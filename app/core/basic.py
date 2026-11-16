"""Step 1 - Basic cleaning: trim whitespace, normalise missing tokens, remove duplicates, convert binary columns.

The operations always run against the ORIGINAL upload and return a new frame, so applying them again with
different options never stacks changes on top of an earlier run.
"""
from __future__ import annotations

import pandas as pd

from .. import config
from .errors import CleanSheetError
from .profiling import NEGATIVE, POSITIVE, detect_binary, to_bool_state

BINARY_TARGETS = {
    "true_false": ("TRUE", "FALSE", "TRUE/FALSE"),
    "yes_no": ("Yes", "No", "Yes/No"),
    "one_zero": ("1", "0", "1/0"),
}
_TOKENS = frozenset(config.MISSING_TOKENS)


# --------------------------------------------------------------------------- #
# Building blocks (each returns a new Series plus a count)
# --------------------------------------------------------------------------- #
def _as_str(s: pd.Series) -> pd.Series:
    return s.where(s.isna(), s.astype(str))


def trim_series(s: pd.Series) -> tuple[pd.Series, int]:
    """Strip leading/trailing whitespace. Returns (series, number of cells that changed)."""
    s = _as_str(s)
    stripped = s.str.strip()
    changed = int((s.notna() & (s != stripped)).sum())
    return stripped, changed


def normalise_missing(s: pd.Series) -> tuple[pd.Series, int]:
    """Blank cells and tokens such as N/A, null, - become missing. Returns (series, cells newly missing)."""
    s = _as_str(s)
    probe = s.str.strip().str.lower()
    is_missing_text = s.notna() & (probe.isin(_TOKENS) | (probe == ""))
    return s.mask(is_missing_text), int(is_missing_text.sum())


def convert_binary_series(s: pd.Series, target: str) -> pd.Series:
    true_text, false_text, _ = BINARY_TARGETS[target]

    def convert(value):
        state = to_bool_state(value)
        return value if state is None else (true_text if state else false_text)

    mapped = s.dropna().map(convert)
    out = s.copy()
    out.loc[mapped.index] = mapped
    return out


# --------------------------------------------------------------------------- #
# Scan (shown right after upload, nothing is changed)
# --------------------------------------------------------------------------- #
def scan(df: pd.DataFrame) -> dict:
    """What basic cleaning would find, judged on a trimmed copy. Used to pre-fill the Step 1 form."""
    cols = []
    ws_cells = token_cells = 0
    probe_cols = {}
    for c in df.columns:
        trimmed, ws = trim_series(df[c])
        normalised, tokens = normalise_missing(trimmed)
        probe_cols[c] = normalised
        ws_cells += ws
        token_cells += tokens
        binary = detect_binary(normalised)
        cols.append({"name": c, "missing_now": int(df[c].isna().sum()), "binary": binary})
    probe = pd.DataFrame(probe_cols, index=df.index)
    return {
        "columns": cols,
        "whitespace_cells": ws_cells,
        "missing_token_cells": token_cells,
        "duplicate_rows": int(probe.duplicated().sum()),
        "binary_columns": [{"name": c["name"], "style": c["binary"]["style"],
                            "numeric_only": c["binary"]["numeric_only"]} for c in cols if c["binary"]],
    }


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #
def clean_options(raw) -> dict:
    """Turn whatever the browser sent into a well-formed options dict (wrong shapes are rejected, not guessed)."""
    if not isinstance(raw, dict):
        raise CleanSheetError("The options were not understood.", 422)
    subset = raw.get("dedupe_columns") or []
    binary = raw.get("binary") or {}
    if not isinstance(subset, list) or not all(isinstance(c, str) for c in subset):
        raise CleanSheetError("The duplicate-matching columns were not understood.", 422)
    if not isinstance(binary, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in binary.items()):
        raise CleanSheetError("The binary-conversion choices were not understood.", 422)
    return {
        "remove_duplicates": bool(raw.get("remove_duplicates")),
        "dedupe_mode": raw.get("dedupe_mode", "all"),
        "dedupe_columns": subset,
        "trim": bool(raw.get("trim")),
        "normalise_missing": bool(raw.get("normalise_missing")),
        "binary": binary,
    }


def validate_options(df: pd.DataFrame, opts: dict) -> None:
    cols = set(df.columns)
    if opts.get("dedupe_mode") not in ("all", "subset"):
        raise CleanSheetError("Choose whether duplicates are matched on all columns or selected columns.", 422)
    if opts.get("remove_duplicates") and opts["dedupe_mode"] == "subset":
        subset = opts.get("dedupe_columns") or []
        if not subset:
            raise CleanSheetError("Select at least one column to match duplicates on.", 422)
        unknown = [c for c in subset if c not in cols]
        if unknown:
            raise CleanSheetError("One of the selected duplicate-matching columns does not exist.", 422)
    for col, target in (opts.get("binary") or {}).items():
        if col not in cols:
            raise CleanSheetError("A binary conversion refers to a column that does not exist.", 422)
        if target not in BINARY_TARGETS and target != "keep":
            raise CleanSheetError("Unknown binary format selected.", 422)


def _skipped_binary(column: str, s: pd.Series, target: str) -> dict:
    """Explain why a requested yes/no conversion was not done (so it is never silently ignored)."""
    vals = s.dropna().astype(str).str.strip()
    other = vals[(vals != "") & ~vals.str.lower().isin(POSITIVE | NEGATIVE)].drop_duplicates().head(3).tolist()
    if other:
        shown = ", ".join(f"'{v if len(v) <= 20 else v[:19] + '…'}'" for v in other)
        reason = (f"Not converted to {BINARY_TARGETS[target][2]}: the column also holds values that are not "
                  f"yes/no states (for example {shown}). Turn on the placeholder option or fix those cells first.")
    else:
        reason = f"Not converted to {BINARY_TARGETS[target][2]}: the column has no yes/no values."
    return {"column": column, "requested": BINARY_TARGETS[target][2], "reason": reason}


def apply_basic(original: pd.DataFrame, opts: dict) -> tuple[pd.DataFrame, dict]:
    """Run basic cleaning on `original` (never modified). Returns (cleaned frame, report)."""
    validate_options(original, opts)
    out_cols = {}
    ws_cells = ws_cols = token_cells = 0
    missing_before = int(original.isna().sum().sum())

    for c in original.columns:
        s = original[c]
        if opts.get("trim"):
            s, n = trim_series(s)
            ws_cells += n
            ws_cols += 1 if n else 0
        if opts.get("normalise_missing"):
            s, n = normalise_missing(s)
            token_cells += n
        out_cols[c] = s
    df = pd.DataFrame(out_cols, index=original.index)

    duplicates_removed = 0
    if opts.get("remove_duplicates"):
        subset = opts["dedupe_columns"] if opts["dedupe_mode"] == "subset" else None
        dup = df.duplicated(subset=subset, keep="first")
        duplicates_removed = int(dup.sum())
        df = df.loc[~dup]

    binary_report = []
    binary_skipped = []
    chosen = opts.get("binary") or {}
    for c in df.columns:
        info = detect_binary(df[c])
        if not info:
            if chosen.get(c, "keep") != "keep":          # asked for, but the column is not two-state any more
                binary_skipped.append(_skipped_binary(c, df[c], chosen[c]))
            continue
        target = chosen.get(c, "keep")
        entry = {"column": c, "detected_as": info["style"], "numeric_only": info["numeric_only"],
                 "converted_to": None}
        if target != "keep":
            df[c] = convert_binary_series(df[c], target)
            entry["converted_to"] = BINARY_TARGETS[target][2]
        binary_report.append(entry)

    report = {
        "original_rows": int(len(original)),
        "cleaned_rows": int(len(df)),
        "columns": int(df.shape[1]),
        "duplicates_removed": duplicates_removed,
        "missing_before": missing_before,
        "missing_tokens_normalised": token_cells,
        "missing_after": int(df.isna().sum().sum()),
        "whitespace_cells_changed": ws_cells,
        "whitespace_columns_changed": ws_cols,
        "binary_columns": binary_report,
        "binary_detected": len(binary_report),
        "binary_converted": sum(1 for b in binary_report if b["converted_to"]),
        "binary_skipped": binary_skipped,
        "warnings": [f"{b['column']}: {b['reason']}" for b in binary_skipped],
    }
    return df, report

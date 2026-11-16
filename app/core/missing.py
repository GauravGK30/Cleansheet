"""Step 2A - advanced missing-value handling, chosen per column and always optional.

Order of work (so results never depend on the order of columns):
  1. rows are removed for columns set to "remove"
  2. formula recovery runs (it may use values recovered by another formula, never guessed ones)
  3. every other fill is computed from the data as analysed (before any row was removed, so it always equals
     the number shown on screen) and written into the rows that remain
Each fill is validated before it is written; a failing column is skipped with a warning.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import relations
from .errors import CleanSheetError
from .validation import ACTION_LABELS, MISSING_ACTIONS_BY_KIND, is_locked
from .values import (format_number, max_decimals, numeric_mask, parse_with_format, to_numbers)

NUMERIC_KINDS = ("numeric", "calculated")
KEY_KINDS = ("identifier", "categorical", "text")


# --------------------------------------------------------------------------- #
# Statistics used for fills
# --------------------------------------------------------------------------- #
def numeric_stats(series: pd.Series, decimals: int) -> dict | None:
    nums = to_numbers(series).dropna()
    if nums.empty:
        return None
    counts = nums.value_counts()
    tied = counts[counts == counts.iloc[0]]
    skew = float(nums.skew()) if len(nums) >= 3 else 0.0
    skew = 0.0 if np.isnan(skew) else skew
    mean, median, mode = float(nums.mean()), float(nums.median()), float(min(tied.index))
    return {
        "mean": format_number(mean, decimals), "median": format_number(median, decimals),
        "mode": format_number(mode, decimals), "mode_tie": len(tied) > 1, "skew": round(skew, 2),
        "n": int(len(nums)),
        "rounded": decimals == 0 and (round(mean) != mean or round(median) != median),
    }


def text_mode(series: pd.Series) -> tuple[str, bool, float] | None:
    s = series.dropna().astype(str)
    if s.empty:
        return None
    counts = s.value_counts()
    tied = sorted(counts[counts == counts.iloc[0]].index)
    return tied[0], len(tied) > 1, float(counts.iloc[0]) / len(s)


# --------------------------------------------------------------------------- #
# Analysis: what can sensibly be done for each column that has missing values
# --------------------------------------------------------------------------- #
def _key_columns(profiles: list[dict]) -> list[str]:
    return [p["name"] for p in profiles
            if p["kind"] in KEY_KINDS and p["non_missing"] and p["unique"] < p["non_missing"]]


def analyse(df: pd.DataFrame, profiles: list[dict]) -> list[dict]:
    keys = _key_columns(profiles)
    return [_analyse_column(df, p, keys) for p in profiles if p["missing"] > 0]


def _analyse_column(df: pd.DataFrame, p: dict, keys: list[str]) -> dict:
    name, kind = p["name"], p["kind"]
    info = {"name": name, "kind": kind, "kind_label": p["kind_label"], "missing": p["missing"],
            "missing_pct": p["missing_pct"], "rows": p["rows"], "locked": is_locked(p), "options": [],
            "stats": None, "mappings": [], "formulas": [], "values": [], "suggested": None,
            "suggested_reason": None, "date_format": p["date_format"], "date_ambiguous": p["date_ambiguous"]}
    if info["locked"]:
        return info
    allowed = MISSING_ACTIONS_BY_KIND[kind]
    s = df[name]
    has_values = p["non_missing"] > 0
    stats = numeric_stats(s, p["max_decimals"]) if kind in NUMERIC_KINDS else None
    info["stats"] = stats
    mode = text_mode(s) if kind not in NUMERIC_KINDS and has_values else None
    if mode:
        info["stats"] = {"mode": mode[0], "mode_tie": mode[1], "mode_share": round(mode[2], 3)}
    if "mapping" in allowed and has_values:
        info["mappings"] = relations.find_mapping_candidates(df, name, keys)
    if "formula" in allowed:
        info["formulas"] = [f for f in p["formulas"] if f["recoverable"] > 0]
    if kind == "boolean":
        info["values"] = sorted(s.dropna().astype(str).str.strip().unique().tolist())[:6]

    available = {
        "mean": bool(stats), "median": bool(stats), "mode": bool(stats or mode),
        "mapping": bool(info["mappings"]), "formula": bool(info["formulas"]),
        "custom": kind != "boolean" or bool(info["values"]), "remove": True, "keep": True,
    }
    info["options"] = [{"value": a, "label": ACTION_LABELS[a]} for a in allowed if available[a]]
    info["suggested"], info["suggested_reason"] = _suggest(kind, stats, mode, info)
    return info


def _suggest(kind, stats, mode, info) -> tuple[str | None, str | None]:
    if kind == "calculated" and info["formulas"]:
        return "formula", "The other columns in these rows are present, so the value can be calculated exactly."
    if kind in NUMERIC_KINDS and stats and kind == "numeric":
        if abs(stats["skew"]) > 1:
            return "median", "The values are skewed, so the median is less affected by extreme values."
        return "mean", "The values are fairly even, so the mean is a reasonable typical value."
    if info["mappings"]:
        m = info["mappings"][0]
        return "mapping", (f"In the other rows every '{m['key']}' value always goes with the same value here, so "
                           f"{m['recoverable']} of {m['total_missing']} can be filled from it. "
                           "Check that the link makes sense for your data.")
    if kind in ("text", "categorical") and mode and mode[2] >= 0.5:
        return "mode", f"'{mode[0]}' makes up {mode[2]:.0%} of the filled values."
    return None, None


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #
def _formula_key(op: str, a: str, b: str) -> tuple:
    """a x b equals b x a, so multiplication ignores the order of its two sources; subtraction does not."""
    return (op,) + (tuple(sorted((a, b))) if op == "multiply" else (a, b))


def _check_data_dependent(df, profiles: dict[str, dict], plan: dict[str, dict]) -> None:
    """Mappings and formulas must be ones this program discovered in the data (never client-supplied)."""
    keys = _key_columns(list(profiles.values()))
    for col, step in plan.items():
        if step["action"] == "mapping":
            ok = [c["key"] for c in relations.find_mapping_candidates(df, col, keys)]
            if step["key"] not in ok:
                raise CleanSheetError(
                    f"'{step['key']}' cannot reliably recover '{col}'. Re-open the options and pick again.", 422)
        if step["action"] == "formula":
            found = [_formula_key(f["op"], f["a"], f["b"]) for f in profiles[col]["formulas"]]
            f = step["formula"]
            if _formula_key(f["op"], f["a"], f["b"]) not in found:
                raise CleanSheetError(f"That formula does not hold for '{col}'.", 422)


def _formula_pass(work: pd.DataFrame, plan: dict[str, dict], profiles: dict[str, dict]) -> dict[str, int]:
    filled = {c: 0 for c, s in plan.items() if s["action"] == "formula"}
    for _ in range(3):                                   # lets margin use a revenue recovered a moment ago
        progress = False
        for col in filled:
            f = plan[col]["formula"]
            vals = relations.formula_values(f["op"], to_numbers(work[f["a"]]), to_numbers(work[f["b"]]))
            rows = work[col].isna() & vals.notna()
            if rows.any():
                dec = profiles[col]["max_decimals"]
                work.loc[rows, col] = vals[rows].map(lambda v: format_number(v, dec))
                filled[col] += int(rows.sum())
                progress = True
        if not progress:
            break
    return filled


def _fill_values(df: pd.DataFrame, work: pd.DataFrame, col: str, step: dict, p: dict
                 ) -> tuple[pd.Series | None, str | None, str | None]:
    """Returns (values aligned to work.index or None, fill description, reason it cannot be done).

    Statistics and mappings are taken from `df`, the data exactly as the person saw it in the analysis, NOT from
    `work` (which has already lost the rows another column asked to remove). Otherwise "Fill with mean (152)" on
    screen could be applied as a different number just because a row was removed for an unrelated column.
    The values are then written only into the rows that survived (`work.index`)."""
    action = step["action"]
    s = df[col]
    if action in ("mean", "median", "mode") and p["kind"] in NUMERIC_KINDS:
        stats = numeric_stats(s, p["max_decimals"])
        if not stats:
            return None, None, "There are no numeric values to calculate it from."
        value = stats[action]
        note = None
        if action == "mode" and stats["mode_tie"]:
            note = "Several values tied; the smallest was used."
        if stats["rounded"] and action in ("mean", "median"):
            note = "Rounded to whole numbers to match the column."
        return pd.Series(value, index=work.index, dtype=object), f"{value}" + (f" ({note})" if note else ""), None
    if action == "mode":
        mode = text_mode(s)
        if not mode:
            return None, None, "The column has no values to take a most common value from."
        return (pd.Series(mode[0], index=work.index, dtype=object), f"'{mode[0]}'" +
                (" (several values tied; the first alphabetically was used)" if mode[1] else ""), None)
    if action == "custom":
        return pd.Series(step["value"], index=work.index, dtype=object), f"'{step['value']}'", None
    if action == "mapping":
        values = relations.mapping_fill(df, col, step["key"]).reindex(work.index)
        if values.notna().sum() == 0:
            return None, None, f"'{step['key']}' no longer gives an unambiguous match for these rows."
        return values, f"from '{step['key']}'", None
    return None, None, "Unsupported action."


def _fill_is_valid(p: dict, values: pd.Series) -> str | None:
    """Check filled values fit the column. Returns a problem description or None."""
    vals = values.dropna()
    if vals.empty:
        return None
    if p["kind"] in NUMERIC_KINDS and not bool(numeric_mask(vals).all()):
        return "The calculated fill is not numeric."
    if p["kind"] == "date" and p["date_format"] and not p["date_ambiguous"]:
        if parse_with_format(vals.astype(str), p["date_format"]).isna().any():
            return "The fill is not a valid date in this column's format."
    return None


def apply_missing(df: pd.DataFrame, profiles: dict[str, dict], plan: dict[str, dict]) -> tuple[pd.DataFrame, dict]:
    """Apply a validated plan to `df` (not modified). Returns (new frame, report)."""
    if not plan:
        return df, {"columns": [], "rows_removed": 0, "cells_filled": 0, "warnings": []}
    _check_data_dependent(df, profiles, plan)

    remove_cols = [c for c, s in plan.items() if s["action"] == "remove"]
    drop = df[remove_cols].isna().any(axis=1) if remove_cols else pd.Series(False, index=df.index)
    if remove_cols and bool(drop.all()):
        raise CleanSheetError("Removing rows with missing values in those columns would delete every row.", 422)
    work = df.loc[~drop].copy()
    formula_filled = _formula_pass(work, plan, profiles)

    result = work.copy()
    rows_report, warnings = [], []
    cells_filled = 0
    for col, step in plan.items():
        p, action = profiles[col], step["action"]
        entry = {"column": col, "kind": p["kind"], "action": action, "label": ACTION_LABELS[action],
                 "status": "applied", "missing_before": int(df[col].isna().sum()), "rows_removed": 0,
                 "filled": 0, "missing_after": 0, "fill_value": None, "warnings": []}
        if action == "remove":
            entry["rows_removed"] = entry["missing_before"]
        elif action == "formula":
            entry["filled"] = formula_filled.get(col, 0)
            entry["fill_value"] = step["formula"] and relations.formula_label(
                col, step["formula"]["op"], step["formula"]["a"], step["formula"]["b"])
            if entry["filled"] == 0:
                entry["entry_note"] = "No row had every source value present."
        else:
            values, described, why = _fill_values(df, work, col, step, p)
            if values is None:
                entry["status"] = "skipped"
                entry["warnings"].append(why)
            else:
                target = work[col].isna() & values.notna()
                problem = _fill_is_valid(p, values[target])
                if problem:
                    entry["status"] = "skipped"
                    entry["warnings"].append(problem)
                else:
                    result.loc[target, col] = values[target]
                    entry["filled"] = int(target.sum())
                    entry["fill_value"] = described
                    expected = int(work[col].isna().sum()) - entry["filled"]
                    if int(result[col].isna().sum()) != expected:      # post-condition check
                        result[col] = work[col]
                        entry.update(status="skipped", filled=0, fill_value=None)
                        entry["warnings"].append("The result failed a consistency check and was not applied.")
        entry["missing_after"] = int(result[col].isna().sum())
        if entry["filled"] and action != "remove":
            left = entry["missing_after"]
            if left:
                entry["warnings"].append(f"{left} value(s) could not be filled and remain missing.")
        cells_filled += entry["filled"]
        warnings += [f"{col}: {w}" for w in entry["warnings"]]
        rows_report.append(entry)

    report = {"columns": rows_report, "rows_removed": int(drop.sum()), "cells_filled": cells_filled,
              "warnings": warnings}
    return result, report

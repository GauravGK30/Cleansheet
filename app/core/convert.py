"""Step 2C - data-type conversion, chosen per column and always optional.

The rule that matters most: a conversion is all-or-nothing. If even one value cannot be converted, the whole
column is skipped, its original values are kept, and a warning says what was wrong. A column is never left
half-converted.

Everything is held as text. A conversion rewrites the text into one canonical form (and records how the
column should be written to an .xlsx file: as numbers, as dates, or as text).
"""
from __future__ import annotations

import pandas as pd

from .. import config
from .errors import CleanSheetError
from .validation import CONVERSIONS_BY_KIND, TEXT_KINDS, is_locked
from .values import (DATE_FORMATS, decimal_text, format_date_column, friendly_date_format, max_decimals,
                     to_numbers, whole_number_text)

CONVERSION_LABELS = {
    "keep": "Keep original", "text": "Text", "integer": "Integer (whole number)", "decimal": "Decimal number",
    "date": "Date (YYYY-MM-DD)",
}
_NOUN = {"integer": "an integer", "decimal": "a decimal number", "text": "text", "date": "a date"}
_HAS_TIME = dict(DATE_FORMATS)
_EXAMPLE_LEN = 30


# --------------------------------------------------------------------------- #
# What the Data types tab offers
# --------------------------------------------------------------------------- #
def options_for(p: dict) -> list[dict]:
    """Conversions that make sense for this column. Nothing irrelevant is offered."""
    out = []
    for action in CONVERSIONS_BY_KIND[p["kind"]]:
        if action == "date" and p["kind"] in TEXT_KINDS and (p["date_ratio"] < 0.5 or not p["date_format"]):
            continue                       # a text column is only offered 'date' when it looks like dates
        label = CONVERSION_LABELS[action]
        if action == "text" and p["kind"] in TEXT_KINDS:
            label = "Text (already text)"
        if action == "date" and p["kind"] == "date":
            label = "Standardize to YYYY-MM-DD"
        if action == "text" and p["kind"] == "identifier":
            label = "Text (keep as text)"
        out.append({"value": action, "label": label})
    return out


def describe_columns(profiles: list[dict]) -> list[dict]:
    """One entry per column that has any conversion besides 'keep'."""
    entries = []
    for p in profiles:
        if is_locked(p):
            continue                       # an unconfirmed column has no operations until the user confirms it
        opts = options_for(p)
        if len(opts) <= 1:
            continue
        entries.append({
            "name": p["name"], "kind": p["kind"], "kind_label": p["kind_label"], "options": opts,
            "default_decimals": min(config.MAX_DECIMAL_PLACES, max(2, p["max_decimals"])),
            "min_decimals": p["max_decimals"],
            "invalid_numbers": (round((1 - p["numeric_ratio"]) * p["non_missing"])
                                if p["kind"] in ("numeric", "calculated") else 0),
            "date_format": p["date_format"], "date_ratio": p["date_ratio"],
            "date_ambiguous": p["date_ambiguous"], "sample": p["sample"],
        })
    return entries


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _examples(values) -> str:
    seen: list[str] = []
    for v in values:
        t = str(v).strip()
        t = t if len(t) <= _EXAMPLE_LEN else t[: _EXAMPLE_LEN - 1] + "…"
        if t not in seen:
            seen.append(t)
        if len(seen) >= config.MAX_INVALID_EXAMPLES:
            break
    return ", ".join(f"'{t}'" for t in seen)


def _map_unique(s: pd.Series, fn) -> pd.Series:
    """Apply fn(text) -> text|None to every non-missing cell, calling it once per distinct value."""
    have = s.dropna().astype(str).str.strip()
    lookup = {v: fn(v) for v in have.unique()}
    out = pd.Series(None, index=s.index, dtype=object)
    out.loc[have.index] = have.map(lookup)
    return out


class _Skip(Exception):
    """Raised inside a converter when the column must be left exactly as it was."""


def _to_integer(s: pd.Series, p: dict, step: dict):
    converted = _map_unique(s, whole_number_text)
    bad = s.notna() & converted.isna()
    if bad.any():
        raise _Skip(f"{int(bad.sum())} value(s) are not whole numbers (for example {_examples(s[bad])}).")
    return converted, {"type": "number", "decimals": 0}, "whole numbers"


def _to_decimal(s: pd.Series, p: dict, step: dict):
    needed = max_decimals(s)
    places = step.get("decimals")
    places = max(2, needed) if places is None else places
    places = min(places, config.MAX_DECIMAL_PLACES)
    if places < needed:
        raise _Skip(f"some values have {needed} decimal places, so {places} would round them. "
                    f"Choose at least {needed}.")
    converted = _map_unique(s, lambda t: decimal_text(t, places))
    bad = s.notna() & converted.isna()
    if bad.any():
        raise _Skip(f"{int(bad.sum())} value(s) are not numbers (for example {_examples(s[bad])}).")
    return converted, {"type": "number", "decimals": places}, f"decimals with {places} place(s)"


def _to_text(s: pd.Series, p: dict, step: dict):
    return s, {"type": "text", "decimals": 0}, "text (values unchanged; saved as text in .xlsx)"


def _to_date(s: pd.Series, p: dict, step: dict):
    fmt = p["date_format"]
    if not fmt:
        raise _Skip("the values do not match a date format CleanSheet can read exactly.")
    if p["date_ambiguous"]:
        raise _Skip("the day/month order is unclear. Choose day-first or month-first first.")
    parsed, invalid = format_date_column(s, fmt)
    if invalid.any():
        raise _Skip(f"{int(invalid.sum())} value(s) are not valid dates in the format {friendly_date_format(fmt)} "
                    f"(for example {_examples(s[invalid])}).")
    if _HAS_TIME.get(fmt, False) and bool((parsed.dropna() != parsed.dropna().dt.normalize()).any()):
        raise _Skip("some values include a time of day, and YYYY-MM-DD would drop it.")
    out = pd.Series(None, index=s.index, dtype=object)
    have = parsed.dropna()
    out.loc[have.index] = have.dt.strftime("%Y-%m-%d")
    return out, {"type": "date", "decimals": 0}, "dates as YYYY-MM-DD"


_CONVERTERS = {"integer": _to_integer, "decimal": _to_decimal, "text": _to_text, "date": _to_date}


def _check_converted(before: pd.Series, after: pd.Series) -> None:
    """Post-condition: same cells missing, same length. A violation is a bug, so nothing is applied."""
    if len(before) != len(after) or not before.isna().equals(after.isna()):
        raise CleanSheetError("A conversion failed its consistency check, so nothing was applied.", 500,
                              "consistency")


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #
def apply_conversions(df: pd.DataFrame, profiles: dict[str, dict], plan: dict[str, dict]
                      ) -> tuple[pd.DataFrame, dict, dict[str, dict]]:
    """Apply a validated conversion plan to `df` (not modified).

    Returns (new frame, report, specs) where specs maps each successfully converted column to how the
    .xlsx writer should store it: {"type": "number"|"date"|"text", "decimals": n}.
    """
    if not plan:
        return df, {"columns": [], "completed": 0, "skipped": 0, "warnings": []}, {}
    result = df.copy()
    entries, warnings, specs = [], [], {}
    completed = skipped = 0
    for col, step in plan.items():
        p, to = profiles[col], step["to"]
        entry = {"column": col, "kind": p["kind"], "to": to, "label": CONVERSION_LABELS[to],
                 "status": "applied", "changed": 0, "detail": None, "warnings": []}
        try:
            values, spec, detail = _CONVERTERS[to](df[col], p, step)
            _check_converted(df[col], values)
            entry["changed"] = int((df[col].notna() & (df[col] != values)).sum())
            entry["detail"] = detail
            result[col] = values
            specs[col] = spec
            completed += 1
        except _Skip as why:
            entry["status"] = "skipped"
            entry["warnings"].append(f"Not converted to {_NOUN[to]}: {why} The original values were kept.")
            skipped += 1
        warnings += [f"{col}: {w}" for w in entry["warnings"]]
        entries.append(entry)
    return result, {"columns": entries, "completed": completed, "skipped": skipped, "warnings": warnings}, specs

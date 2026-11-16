"""Validation of everything the browser sends. Nothing here trusts the client: unknown columns, actions
that do not suit a column's kind, and malformed values are rejected with a plain-language message.
"""
from __future__ import annotations

import re

import pandas as pd

from .. import config
from .errors import CleanSheetError
from .profiling import CONFIRMABLE_KINDS
from .values import DATE_FORMATS, clean_number_text, parse_with_format

MISSING_ACTIONS_BY_KIND = {
    "numeric": ("mean", "median", "mode", "custom", "remove", "keep"),
    "calculated": ("formula", "custom", "remove", "keep"),
    "text": ("mode", "custom", "mapping", "remove", "keep"),
    "categorical": ("mode", "custom", "mapping", "remove", "keep"),
    "identifier": ("mapping", "custom", "remove", "keep"),
    "date": ("mapping", "custom", "remove", "keep"),
    "boolean": ("custom", "remove", "keep"),
}
ACTION_LABELS = {
    "mean": "Fill with mean", "median": "Fill with median", "mode": "Fill with most common value",
    "custom": "Fill with a value I type", "mapping": "Recover from a related column",
    "formula": "Recalculate from other columns", "remove": "Remove rows with a missing value",
    "keep": "Keep missing values",
}
TEXT_KINDS = ("text", "categorical")
CASES = ("preserve", "lower", "upper", "title")
CONVERSIONS_BY_KIND = {
    "text": ("keep", "text", "date"), "categorical": ("keep", "text", "date"),
    "numeric": ("keep", "integer", "decimal", "text"), "calculated": ("keep", "integer", "decimal", "text"),
    "date": ("keep", "date", "text"), "identifier": ("keep", "text"), "boolean": ("keep",),
}
KNOWN_DATE_FORMATS = {f for f, _ in DATE_FORMATS}
MAX_TEXT_RULES = 10
MAX_VALUE_LEN = 200
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _fail(message: str) -> None:
    raise CleanSheetError(message, 422, "invalid_selection")


def _profile(profiles: dict[str, dict], col) -> dict:
    if not isinstance(col, str) or col not in profiles:
        _fail("One of the selected columns does not exist in this dataset.")
    return profiles[col]


def is_locked(p: dict) -> bool:
    """Uncertain column that the user has not confirmed yet."""
    return bool(p["needs_confirmation"]) and not p["confirmed"]


def _require_confirmed(p: dict) -> None:
    if is_locked(p):
        _fail(f"Confirm the type of column '{p['name']}' before choosing an operation for it.")


# --------------------------------------------------------------------------- #
# Type confirmations
# --------------------------------------------------------------------------- #
def validate_overrides(overrides, df: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    for col, kind in (overrides or {}).items():
        if col not in df.columns:
            _fail("A type confirmation refers to a column that does not exist.")
        if kind not in CONFIRMABLE_KINDS:
            _fail("Unknown column type selected.")
        out[col] = kind
    return out


def validate_date_formats(date_formats, df: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    for col, fmt in (date_formats or {}).items():
        if col not in df.columns or fmt not in KNOWN_DATE_FORMATS:
            _fail("A date-order choice is not valid.")
        out[col] = fmt
    return out


# --------------------------------------------------------------------------- #
# Missing-value plan
# --------------------------------------------------------------------------- #
def normalise_custom_value(p: dict, series: pd.Series, value) -> str:
    """The text that will be written into the cells, checked against the column's kind."""
    name, kind = p["name"], p["kind"]
    text = "" if value is None else str(value).strip()
    if not text:
        _fail(f"Enter a value to fill '{name}' with.")
    if len(text) > MAX_VALUE_LEN or _CONTROL.search(text):
        _fail(f"The value for '{name}' is too long or contains unsupported characters.")
    if kind in ("numeric", "calculated"):
        number = clean_number_text(text)
        if number is None:
            _fail(f"'{name}' holds numbers, so the value must be a number.")
        return number
    if kind == "date":
        if p["date_ambiguous"]:
            _fail(f"The day/month order of '{name}' is unclear. Choose day-first or month-first for it first.")
        iso = parse_with_format(pd.Series([text]), "%Y-%m-%d")
        if iso.isna().iloc[0]:
            _fail(f"Enter the date for '{name}' as YYYY-MM-DD.")
        fmt = p["date_format"]
        return iso.iloc[0].strftime(fmt) if fmt else text
    if kind == "boolean":
        existing = {str(v).strip().lower(): str(v).strip() for v in series.dropna().unique()}
        if text.lower() not in existing:
            _fail(f"For '{name}', choose one of the values already in the column.")
        return existing[text.lower()]
    return text


def validate_missing_plan(plan, df: pd.DataFrame, profiles: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for col, step in (plan or {}).items():
        p = _profile(profiles, col)
        action = (step or {}).get("action", "keep")
        if action == "keep":
            continue
        if action not in MISSING_ACTIONS_BY_KIND[p["kind"]]:
            _fail(f"'{ACTION_LABELS.get(action, action)}' is not available for the {p['kind_label'].lower()} "
                  f"column '{col}'.")
        _require_confirmed(p)
        entry = {"action": action, "value": None, "key": None, "formula": None}
        if action == "custom":
            entry["value"] = normalise_custom_value(p, df[col], step.get("value"))
        elif action == "mapping":
            key = step.get("key")
            if not isinstance(key, str) or key not in df.columns or key == col:
                _fail(f"Choose which related column to recover '{col}' from.")
            entry["key"] = key
        elif action == "formula":
            f = step.get("formula") or {}
            if f.get("op") not in ("multiply", "subtract") or f.get("a") not in df.columns \
                    or f.get("b") not in df.columns:
                _fail(f"Choose a formula for '{col}'.")
            entry["formula"] = {"op": f["op"], "a": f["a"], "b": f["b"]}
        out[col] = entry
    return out


# --------------------------------------------------------------------------- #
# Text standardisation plan
# --------------------------------------------------------------------------- #
def validate_text_plan(plan, df: pd.DataFrame, profiles: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for col, step in (plan or {}).items():
        p = _profile(profiles, col)
        step = step or {}
        case = step.get("case", "preserve")
        if case not in CASES:
            _fail("Unknown text case selected.")
        rules = []
        for r in (step.get("replace") or [])[:MAX_TEXT_RULES + 1]:
            find = "" if r.get("find") is None else str(r["find"])
            if find == "":
                continue                                    # an empty 'find' means the row was left blank
            repl = "" if r.get("replace") is None else str(r["replace"])
            if len(find) > MAX_VALUE_LEN or len(repl) > MAX_VALUE_LEN:
                _fail(f"A find/replace value for '{col}' is too long.")
            rules.append({"find": find, "replace": repl, "match_case": bool(r.get("match_case")),
                          "whole_cell": bool(r.get("whole_cell"))})
        if len(rules) > MAX_TEXT_RULES:
            _fail(f"At most {MAX_TEXT_RULES} find/replace rules are allowed per column.")
        entry = {"case": case, "trim": bool(step.get("trim")), "collapse": bool(step.get("collapse")),
                 "replace": rules}
        if entry["case"] == "preserve" and not (entry["trim"] or entry["collapse"] or rules):
            continue
        if p["kind"] == "identifier":
            _fail(f"'{col}' is an identifier column and is protected from text changes.")
        if p["kind"] not in TEXT_KINDS:
            _fail(f"Text standardization is only available for text columns; '{col}' is "
                  f"{p['kind_label'].lower()}.")
        _require_confirmed(p)
        out[col] = entry
    return out


# --------------------------------------------------------------------------- #
# Data-type conversion plan
# --------------------------------------------------------------------------- #
def validate_conversion_plan(plan, df: pd.DataFrame, profiles: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for col, step in (plan or {}).items():
        p = _profile(profiles, col)
        to = (step or {}).get("to", "keep")
        if to == "keep":
            continue
        if to not in CONVERSIONS_BY_KIND[p["kind"]]:
            _fail(f"Converting the {p['kind_label'].lower()} column '{col}' to '{to}' is not available.")
        if to == "date" and p["kind"] in TEXT_KINDS and p["date_ratio"] < 0.5:
            _fail(f"The values in '{col}' do not look like dates.")
        if to == "date" and p["date_ambiguous"]:
            _fail(f"The day/month order of '{col}' is unclear. Choose day-first or month-first for it first.")
        _require_confirmed(p)
        entry = {"to": to}
        if to == "decimal":
            places = step.get("decimals")
            if places is not None:
                if isinstance(places, bool) or not isinstance(places, int) \
                        or not 0 <= places <= config.MAX_DECIMAL_PLACES:
                    _fail(f"Decimal places for '{col}' must be a whole number from 0 to {config.MAX_DECIMAL_PLACES}.")
                entry["decimals"] = places
        out[col] = entry
    return out

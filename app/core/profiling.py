"""Rule-based column profiling. No machine learning: fixed rules over column names AND actual values.

Kinds: numeric, calculated, text, categorical, date, identifier, boolean.
A column name alone never decides the kind. When the evidence is mixed the profile is flagged
`needs_confirmation` and the user is asked instead of the program guessing.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import relations
from .values import (detect_date_format_of, distinct, max_decimals_of_texts, number_like, to_numbers)

KINDS = ("numeric", "calculated", "text", "categorical", "date", "identifier", "boolean")
CONFIRMABLE_KINDS = ("numeric", "text", "categorical", "date", "identifier", "boolean")
KIND_LABELS = {"numeric": "Number", "calculated": "Calculated number", "text": "Text",
               "categorical": "Category", "date": "Date", "identifier": "Identifier", "boolean": "Yes/No flag"}

ID_TOKENS = {"id", "uid", "uuid", "guid", "sku", "code", "ref", "key", "no", "num", "nr", "number",
             "zip", "postal", "isbn", "upc", "ean", "barcode"}
DATE_TOKENS = {"date", "dt", "day", "time", "timestamp", "datetime", "created", "updated", "dob",
               "birth", "expiry", "expiration", "due", "deadline"}
BOOL_FIRST_TOKENS = {"is", "has", "was", "can", "did", "does", "will", "should"}
BOOL_TOKENS = {"flag", "active", "enabled", "anomaly", "anomalous", "valid", "paid", "returned"}
CALC_TOKENS = {"revenue", "total", "subtotal", "cost", "margin", "profit", "sales", "amount"}

POSITIVE = {"true", "t", "yes", "y", "1"}
NEGATIVE = {"false", "f", "no", "n", "0"}
_STYLES = {frozenset({"true", "false"}): "TRUE/FALSE", frozenset({"yes", "no"}): "Yes/No",
           frozenset({"1", "0"}): "1/0", frozenset({"y", "n"}): "Y/N", frozenset({"t", "f"}): "T/F"}

_INT_TEXT = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)$")


def name_tokens(name: str) -> list[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))
    return [t.lower() for t in re.findall(r"[A-Za-z]+|\d+", spaced)]


def _hint(name: str, vocabulary: set[str]) -> bool:
    return any(t in vocabulary for t in name_tokens(name))


def detect_binary(series: pd.Series) -> dict | None:
    """Is this column a two-state flag (TRUE/FALSE, Yes/No, 1/0, Y/N, T/F)? Decided from the values only."""
    return binary_of(distinct(series)[1])


def binary_of(texts: pd.Series) -> dict | None:
    """detect_binary from the column's different values (already stripped)."""
    s = texts[texts != ""]
    if s.empty:
        return None
    originals = sorted(s.unique().tolist())
    lowered = {v.lower() for v in originals}
    if not lowered <= (POSITIVE | NEGATIVE):
        return None
    has_pos, has_neg = bool(lowered & POSITIVE), bool(lowered & NEGATIVE)
    numeric_only = lowered <= {"1", "0"}
    if not (has_pos and has_neg):
        if numeric_only or len(lowered) > 1 and not any(v.isalpha() for v in lowered):
            return None                      # a column that is only 1s (or only 0s) is a number
    style = _STYLES.get(frozenset(lowered), "mixed")
    return {"style": style, "values": originals[:6], "numeric_only": numeric_only}


def to_bool_state(value: str) -> bool | None:
    v = str(value).strip().lower()
    return True if v in POSITIVE else False if v in NEGATIVE else None


def _signature(values: pd.Series) -> pd.Series:
    sig = values.str.replace(r"[A-Za-z]+", "A", regex=True)
    return sig.str.replace(r"\d+", "9", regex=True)


def _empty_profile(name: str, index: int, n: int, missing: int) -> dict:
    return {"name": name, "index": index, "kind": "text", "kind_label": KIND_LABELS["text"],
            "confidence": "low", "needs_confirmation": False, "confirmed": False, "alternatives": [],
            "reasons": ["The column has no values."], "rows": n, "missing": missing,
            "missing_pct": round(100 * missing / n, 1) if n else 0.0, "non_missing": 0, "unique": 0,
            "numeric_ratio": 0.0, "date_ratio": 0.0, "date_format": None, "date_ambiguous": False,
            "date_candidates": [], "integer_like": False, "max_decimals": 0, "leading_zeros": False,
            "binary": None, "sample": [], "formulas": []}


def profile_column(series: pd.Series, name: str, index: int = 0, override: str | None = None,
                   date_format: str | None = None) -> dict:
    n = len(series)
    missing = int(series.isna().sum())
    nn = n - missing
    if nn == 0:
        p = _empty_profile(name, index, n, missing)
        if override in CONFIRMABLE_KINDS:
            p.update(kind=override, kind_label=KIND_LABELS[override], confirmed=True)
        return p

    # Every rule below runs once per DIFFERENT value (`texts`), weighted by how many cells hold it (`w`).
    # The answers are identical to running over every row, but far faster on big files.
    codes, texts = distinct(series)
    w = np.bincount(codes[codes >= 0], minlength=len(texts))
    uniq = int(texts.nunique())
    is_num = number_like(texts).to_numpy(dtype=bool)
    numeric_ratio = float(w[is_num].sum()) / nn
    integer_like = numeric_ratio >= 0.9 and bool(texts[is_num].map(lambda x: bool(_INT_TEXT.match(x))).all())
    digits_only = texts.str.fullmatch(r"\d+").to_numpy(dtype=bool)
    digits_share = float(w[digits_only].sum()) / nn
    lead_zero = int(w[texts.str.fullmatch(r"0\d+").to_numpy(dtype=bool)].sum())
    date_hint = _hint(name, DATE_TOKENS)
    id_hint = _hint(name, ID_TOKENS)

    date_ratio, date_fmt, date_amb, date_cands = 0.0, None, False, []
    if numeric_ratio < 0.9 or (date_hint and digits_share >= 0.9):
        det = detect_date_format_of(texts, w, allow_compact=date_hint)
        date_ratio, date_fmt, date_amb, date_cands = det.ratio, det.format, det.ambiguous, det.candidates

    if date_amb and date_format in date_cands:      # the user settled day-first vs month-first
        date_fmt, date_amb = date_format, False

    binary = binary_of(texts)
    p = {
        "name": name, "index": index, "rows": n, "missing": missing,
        "missing_pct": round(100 * missing / n, 1), "non_missing": nn, "unique": uniq,
        "numeric_ratio": round(numeric_ratio, 4), "date_ratio": round(date_ratio, 4),
        "date_format": date_fmt, "date_ambiguous": date_amb, "date_candidates": date_cands,
        "integer_like": integer_like, "max_decimals": max_decimals_of_texts(texts),
        "leading_zeros": lead_zero > 0 and digits_share >= 0.9,
        "binary": binary, "sample": texts.drop_duplicates().head(3).tolist(), "formulas": [],
        "confirmed": False,
    }
    kind, confidence, confirm, alts, reasons = _decide(
        name, texts, w, nn, uniq, numeric_ratio, integer_like, lead_zero, digits_only, digits_share,
        date_ratio, date_hint, id_hint, binary, p["max_decimals"])
    if override in CONFIRMABLE_KINDS:
        kind, confidence, confirm, alts = override, "high", False, []
        reasons = ["Type set by you."]
        p["confirmed"] = True
    p.update(kind=kind, kind_label=KIND_LABELS[kind], confidence=confidence,
             needs_confirmation=confirm, alternatives=alts, reasons=reasons)
    return p


def _decide(name, texts, w, nn, uniq, numeric_ratio, integer_like, lead_zero, digits_only, digits_share,
            date_ratio, date_hint, id_hint, binary, decimals):
    """The classification rules, in priority order. Returns (kind, confidence, confirm, alternatives, reasons).

    `texts` are the column's different values (stripped) and `w` how many cells hold each; `digits_only` marks
    the digits-only texts."""
    if binary:
        flag_name = bool(name_tokens(name)) and (name_tokens(name)[0] in BOOL_FIRST_TOKENS
                                                 or _hint(name, BOOL_TOKENS))
        if binary["numeric_only"] and not flag_name:
            return ("boolean", "medium", True, ["numeric"],
                    ["Only the values 1 and 0 appear: this may be a flag or a number."])
        return "boolean", "high", False, [], [f"Only two states appear ({binary['style']})."]

    if lead_zero and digits_share >= 0.9 and decimals == 0:
        strong = id_hint or lead_zero / nn >= 0.05
        return ("identifier", "high" if strong else "medium", not strong, ["numeric"],
                ["Numbers with leading zeros must stay text so the zeros are kept."])

    if date_ratio >= 0.9:
        why = "Values match a date format" + ("" if date_ratio == 1 else f" ({date_ratio:.0%} of them)") + "."
        return "date", "high" if date_ratio == 1 else "medium", False, [], [why]
    if date_ratio >= 0.5:
        # Same rule as numbers (50-90% fit): ask rather than guess, whether or not the name mentions dates.
        why = (f"The name suggests dates and {date_ratio:.0%} of values look like dates." if date_hint
               else f"{date_ratio:.0%} of values look like dates and the rest do not.")
        return "date", "medium", True, ["text"], [why]

    lengths = texts.str.len()
    top_share = float(pd.Series(w).groupby(_signature(texts).to_numpy()).sum().max()) / nn
    has_letters = bool(texts.str.contains(r"[A-Za-z]").any())
    has_digits = bool(texts.str.contains(r"\d").any())
    no_spaces = not texts.str.contains(r"\s").any()
    code_like = (top_share >= 0.9 and has_letters and has_digits and no_spaces
                 and float((lengths.to_numpy() * w).sum()) / nn <= 30 and numeric_ratio < 0.5)
    if code_like and (id_hint or uniq / nn >= 0.5):
        return "identifier", "high" if id_hint else "medium", False, [], ["Values follow one repeating code pattern."]
    if id_hint:
        if numeric_ratio >= 0.9 and integer_like:
            return "identifier", "high", False, [], ["The name and the whole-number values both suggest an ID."]
        if numeric_ratio < 0.5 and no_spaces:
            return "identifier", "high", False, [], ["The name and the compact text values both suggest an ID."]
        if numeric_ratio >= 0.9:
            return ("numeric", "medium", True, ["identifier"],
                    ["The name suggests an ID but the values have decimals."])

    if numeric_ratio >= 0.9:
        code_digits = (integer_like and bool(digits_only.all()) and lengths.nunique() == 1
                       and int(lengths.iloc[0]) >= 5 and uniq / nn >= 0.5)
        if code_digits:
            return ("numeric", "medium", True, ["identifier"],
                    ["Same-length numbers with many different values may be codes rather than amounts."])
        return "numeric", "high", False, [], ["Values are numbers."]
    if numeric_ratio >= 0.5:
        return ("numeric", "medium", True, ["text"],
                [f"{numeric_ratio:.0%} of values are numbers; the rest are text."])

    if (uniq <= 50 and uniq / nn <= 0.5) or uniq <= 12:
        return "categorical", "high", False, [], [f"Only {uniq} different values."]
    return "text", "high", False, [], ["Free text with many different values."]


def profile_frame(df: pd.DataFrame, overrides: dict[str, str] | None = None,
                  find_formulas: bool = True, date_formats: dict[str, str] | None = None) -> list[dict]:
    """Profile every column. `overrides` maps column -> kind chosen by the user to settle an uncertain one;
    `date_formats` maps column -> the day/month order the user picked for an ambiguous date column."""
    overrides = overrides or {}
    date_formats = date_formats or {}
    profiles = [profile_column(df[c], c, i, overrides.get(c), date_formats.get(c))
                for i, c in enumerate(df.columns)]
    if find_formulas:
        _mark_calculated(df, profiles, overrides)
    return profiles


def _mark_calculated(df: pd.DataFrame, profiles: list[dict], overrides: dict[str, str]) -> None:
    numeric = [p["name"] for p in profiles if p["kind"] == "numeric" and p["numeric_ratio"] >= 0.9]
    if len(numeric) < 3:
        return
    nums = {c: to_numbers(df[c]) for c in numeric}
    for p in profiles:
        c = p["name"]
        if c not in nums or c in overrides:
            continue
        calc_name = _hint(c, CALC_TOKENS)
        if p["missing"] == 0 and not calc_name:
            continue
        found = relations.find_formula_candidates(df, c, nums, numeric)
        if not found:
            continue
        p["formulas"] = found
        p["kind"], p["kind_label"] = "calculated", KIND_LABELS["calculated"]
        p["confidence"] = "high" if calc_name else "medium"
        p["needs_confirmation"] = False
        p["alternatives"] = ["numeric"]
        p["reasons"] = [f"Values follow a formula: {found[0]['label']}."]


def public_profile(p: dict) -> dict:
    """The part of a profile sent to the browser."""
    keys = ("name", "index", "kind", "kind_label", "confidence", "needs_confirmation", "confirmed",
            "alternatives", "reasons", "rows", "missing", "missing_pct", "non_missing", "unique",
            "numeric_ratio", "date_ratio", "date_format", "date_ambiguous", "date_candidates",
            "integer_like", "max_decimals", "leading_zeros", "sample", "formulas")
    out = {k: p[k] for k in keys}
    out["binary_style"] = p["binary"]["style"] if p.get("binary") else None
    return out


def count_missing(df: pd.DataFrame) -> int:
    return int(df.isna().sum().sum())

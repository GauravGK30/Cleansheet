"""Deterministic parsing helpers for numbers and dates.

Everything in CleanSheet is held as text (so identifiers and leading zeros survive) and these helpers
decide, with fixed rules, whether a piece of text is a number or a date. No guessing libraries are used:
dates are only recognised in the explicit formats listed below.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #
# Safety limits: an exponent is at most two digits and the text at most 40 characters, so every accepted
# number is finite (|x| < 1e140) and no helper can be made to build a gigantic integer from "1e999999999".
MAX_NUMBER_TEXT_LEN = 40
_PLAIN_NUM = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d{1,2})?$")
_THOUSANDS_NUM = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_CANONICAL_NUM = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")


def _as_text(series: pd.Series) -> pd.Series:
    """Non-missing values of a series as stripped strings (index preserved)."""
    s = series.dropna()
    if s.empty:
        return s.astype(object)
    return s.astype(str).str.strip()


def distinct(series: pd.Series) -> tuple[np.ndarray, pd.Series]:
    """The different non-missing values of a column, as stripped text, plus a row -> value lookup.

    Returns (codes, texts): `texts[codes[i]]` is row i's value (codes[i] is -1 for a missing cell), and `texts`
    lists values in order of first appearance. Text rules (regex, number parsing...) can then run once per
    different value instead of once per row, which is what keeps a 500,000-row column fast: most columns
    repeat the same few values over and over. `texts` may hold two entries that differ only by spaces.
    """
    codes, uniques = pd.factorize(series)
    if len(uniques) == 0:
        return codes, pd.Series([], dtype=object)
    return codes, pd.Series(uniques).astype(str).str.strip()


def spread(codes: np.ndarray, per_distinct, fill, dtype) -> np.ndarray:
    """Copy one result per distinct value back to every row (rows with a missing cell get `fill`)."""
    out = np.full(len(codes), fill, dtype=dtype)
    have = codes >= 0
    out[have] = np.asarray(per_distinct)[codes[have]]
    return out


def number_like(s: pd.Series) -> pd.Series:
    """Boolean Series over already-stripped text: plain number or thousands-separated number, within limits."""
    return ((s.str.fullmatch(_PLAIN_NUM) | s.str.fullmatch(_THOUSANDS_NUM))
            & (s.str.len() <= MAX_NUMBER_TEXT_LEN))


def numeric_mask(series: pd.Series) -> pd.Series:
    """Boolean Series (same index as `series`): True where the cell holds a plain number."""
    codes, texts = distinct(series)
    if texts.empty:
        return pd.Series(False, index=series.index)
    ok = number_like(texts).to_numpy(dtype=bool)
    return pd.Series(spread(codes, ok, False, bool), index=series.index)


def to_numbers(series: pd.Series) -> pd.Series:
    """Float Series: the numeric value of each cell, NaN where missing or not a number."""
    codes, texts = distinct(series)
    if texts.empty:
        return pd.Series(np.nan, index=series.index, dtype="float64")
    ok = number_like(texts).to_numpy(dtype=bool)
    values = np.full(len(texts), np.nan)
    if ok.any():
        good = texts[ok].str.replace(",", "", regex=False)
        values[ok] = pd.to_numeric(good, errors="coerce").astype("float64").to_numpy()
    return pd.Series(spread(codes, values, np.nan, "float64"), index=series.index, dtype="float64")


def decimals_of(text: str) -> int:
    """Digits after the decimal point in a numeric string (exponent ignored)."""
    text = text.strip().replace(",", "")
    mantissa = re.split(r"[eE]", text)[0]
    return len(mantissa.split(".")[1]) if "." in mantissa else 0


def max_decimals_of_texts(texts: pd.Series, cap: int = 10) -> int:
    """Most decimal places among the number-like entries of already-stripped distinct text."""
    if texts.empty:
        return 0
    ok = texts[number_like(texts)]
    if ok.empty:
        return 0
    return min(cap, int(ok.map(decimals_of).max()))


def max_decimals(series: pd.Series, cap: int = 10) -> int:
    return max_decimals_of_texts(distinct(series)[1], cap)


def format_number(value: float, decimals: int) -> str:
    """Format with fixed decimals, rounding half up (so 2.5 -> 3, not banker's rounding)."""
    q = Decimal(1).scaleb(-decimals) if decimals > 0 else Decimal(1)
    with localcontext() as ctx:
        ctx.prec = 400                      # the default 28 digits would fail on very large values
        return format(Decimal(repr(float(value))).quantize(q, rounding=ROUND_HALF_UP), "f")


def clean_number_text(text: str) -> str | None:
    """Return the number as plain text (thousand separators removed) or None if it is not a number."""
    t = str(text).strip()
    if len(t) > MAX_NUMBER_TEXT_LEN:
        return None
    if _PLAIN_NUM.match(t):
        return t
    if _THOUSANDS_NUM.match(t):
        return t.replace(",", "")
    return None


def is_canonical_number(text: str) -> bool:
    """Plain digits, optional minus/decimals, no leading zeros, <= 15 significant digits."""
    return bool(_CANONICAL_NUM.match(text)) and len(text.replace("-", "").replace(".", "")) <= 15


def whole_number_text(text: str) -> str | None:
    """'12', '12.0', '1,200', '1e3' -> '12', '12', '1200', '1000'. None when not a whole number."""
    cleaned = clean_number_text(text)
    if cleaned is None:
        return None
    try:
        d = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not d.is_finite() or d != d.to_integral_value():
        return None
    return str(int(d))


def decimal_text(text: str, decimals: int) -> str | None:
    cleaned = clean_number_text(text)
    if cleaned is None:
        return None
    try:
        d = Decimal(cleaned)
    except InvalidOperation:
        return None
    return format(d, f".{decimals}f") if d.is_finite() else None


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #
# (strptime format, has_time). Order does not matter: the best-matching format wins.
DATE_FORMATS: tuple[tuple[str, bool], ...] = (
    ("%Y-%m-%d", False), ("%Y/%m/%d", False),
    ("%d-%m-%Y", False), ("%m-%d-%Y", False),
    ("%d/%m/%Y", False), ("%m/%d/%Y", False),
    ("%d.%m.%Y", False),
    ("%d-%b-%Y", False), ("%d %b %Y", False), ("%d %B %Y", False),
    ("%b %d, %Y", False), ("%B %d, %Y", False),
    ("%Y-%m-%d %H:%M:%S", True), ("%Y-%m-%d %H:%M", True), ("%Y-%m-%dT%H:%M:%S", True),
    ("%d/%m/%Y %H:%M:%S", True), ("%m/%d/%Y %H:%M:%S", True),
    ("%d/%m/%Y %H:%M", True), ("%m/%d/%Y %H:%M", True),
)
COMPACT_FORMAT = ("%Y%m%d", False)  # only tried when the column name suggests a date

# Pairs that differ only by day/month order: both can fit the same text ("03/04/2024").
_DAY_MONTH_PAIRS = {
    "%d-%m-%Y": "%m-%d-%Y", "%m-%d-%Y": "%d-%m-%Y",
    "%d/%m/%Y": "%m/%d/%Y", "%m/%d/%Y": "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S": "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S": "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M": "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M": "%d/%m/%Y %H:%M",
}


_FRIENDLY_TOKENS = (("%Y", "YYYY"), ("%m", "MM"), ("%d", "DD"), ("%H", "HH"), ("%M", "mm"), ("%S", "ss"),
                    ("%B", "Month"), ("%b", "Mon"))


def friendly_date_format(fmt: str) -> str:
    """'%d/%m/%Y' -> 'DD/MM/YYYY'. Warnings are for people, who should never have to read strptime codes."""
    for code, shown in _FRIENDLY_TOKENS:
        fmt = fmt.replace(code, shown)
    return fmt


def parse_with_format(values: pd.Series, fmt: str) -> pd.Series:
    """datetime64 Series, NaT where a value does not match `fmt` exactly."""
    return pd.to_datetime(values, format=fmt, errors="coerce")


class DateDetection:
    """Result of looking for one consistent date format in a column."""

    def __init__(self) -> None:
        self.format: str | None = None
        self.has_time: bool = False
        self.ratio: float = 0.0              # share of non-missing cells that parse with `format`
        self.ambiguous: bool = False         # day/month order cannot be told apart from the data
        self.candidates: list[str] = []      # formats to choose from when ambiguous


def detect_date_format(series: pd.Series, allow_compact: bool = False) -> DateDetection:
    """Find the single format that parses the most non-missing cells."""
    codes, texts = distinct(series)
    return detect_date_format_of(texts, np.bincount(codes[codes >= 0], minlength=len(texts)), allow_compact)


def detect_date_format_of(texts: pd.Series, weights: np.ndarray, allow_compact: bool = False) -> DateDetection:
    """Same as detect_date_format, from distinct stripped texts and how many cells hold each (parsed once each)."""
    det = DateDetection()
    if texts.empty:
        return det
    uniques = texts.reset_index(drop=True)
    total = int(weights.sum())
    best: list[tuple[str, bool, float]] = []
    top = 0.0
    formats = DATE_FORMATS + ((COMPACT_FORMAT,) if allow_compact else ())
    for fmt, has_time in formats:
        parsed = parse_with_format(uniques, fmt)
        ratio = float(weights[parsed.notna().to_numpy()].sum()) / total
        if ratio <= 0:
            continue
        if ratio > top + 1e-12:
            best, top = [(fmt, has_time, ratio)], ratio
        elif abs(ratio - top) <= 1e-12:
            best.append((fmt, has_time, ratio))
    if not best:
        return det
    det.ratio = top
    # A format that also fits time-less text would tie with its shorter sibling only if values carry time;
    # prefer the format with time when it ties (it is strictly more specific).
    best.sort(key=lambda b: (not b[1], b[0]))
    det.format, det.has_time = best[0][0], best[0][1]
    fmts = [b[0] for b in best]
    pair = _DAY_MONTH_PAIRS.get(det.format)
    if pair and pair in fmts:
        det.ambiguous = True
        det.candidates = sorted({det.format, pair})
    return det


def format_date_column(series: pd.Series, fmt: str) -> tuple[pd.Series, pd.Series]:
    """Parse a column with `fmt`. Returns (datetime Series, mask of cells that are non-missing but invalid)."""
    non_missing = series.notna()
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    s = _as_text(series)
    if not s.empty:
        uniq = pd.Series(s.unique())
        lookup = dict(zip(uniq, parse_with_format(uniq, fmt)))
        parsed.loc[s.index] = pd.to_datetime(s.map(lookup))
    invalid = non_missing & parsed.isna()
    return parsed, invalid

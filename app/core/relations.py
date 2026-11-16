"""Relationships between columns that make missing values recoverable without guessing.

* mapping:  key column -> target column, only when every key value maps to exactly one target value
* formula:  target = a x b  or  target = a - b, only when it holds on (almost) every complete row

Both are discovered from the data itself; the client never supplies a formula or a mapping.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .values import max_decimals

MAX_FORMULA_COLS = 20      # numeric columns considered as formula sources (keeps the pair search small)
MAX_KEY_COLS = 25          # key columns tried when looking for a mapping
FORMULA_MIN_ROWS = 5       # complete rows needed before a formula is believed
FORMULA_MIN_MATCH = 0.98   # share of complete rows that must satisfy the formula


# --------------------------------------------------------------------------- #
# Formulas
# --------------------------------------------------------------------------- #
def formula_label(target: str, op: str, a: str, b: str) -> str:
    return f"{target} = {a} × {b}" if op == "multiply" else f"{target} = {a} − {b}"


def formula_values(op: str, a: pd.Series, b: pd.Series) -> pd.Series:
    return a * b if op == "multiply" else a - b


def find_formula_candidates(df: pd.DataFrame, target: str, nums: dict[str, pd.Series],
                            numeric_cols: list[str]) -> list[dict]:
    """Formulas that reproduce `target` from two other numeric columns. `nums` maps column -> floats."""
    t = nums[target].to_numpy()
    t_ok = ~np.isnan(t)
    if t_ok.sum() < FORMULA_MIN_ROWS or len(np.unique(t[t_ok])) < 2:
        return []
    tol = 0.5 * 10 ** (-max_decimals(df[target])) + 1e-9
    sources = [c for c in numeric_cols if c != target and nums[c].nunique() >= 2]
    sources = sorted(sources, key=lambda c: -int(nums[c].notna().sum()))[:MAX_FORMULA_COLS]
    arrays = {c: nums[c].to_numpy() for c in sources}
    out: list[dict] = []

    def consider(op: str, a: str, b: str) -> None:
        av, bv = arrays[a], arrays[b]
        complete = t_ok & ~np.isnan(av) & ~np.isnan(bv)
        n = int(complete.sum())
        if n < FORMULA_MIN_ROWS:
            return
        expected = av[complete] * bv[complete] if op == "multiply" else av[complete] - bv[complete]
        actual = t[complete]
        if int((actual != 0).sum()) < 3:
            return
        ratio = float((np.abs(actual - expected) <= tol + 1e-9 * np.abs(actual)).mean())
        if ratio < FORMULA_MIN_MATCH:
            return
        recoverable = int((~t_ok & ~np.isnan(av) & ~np.isnan(bv)).sum())
        out.append({"op": op, "a": a, "b": b, "label": formula_label(target, op, a, b),
                    "match_ratio": round(ratio, 4), "recoverable": recoverable})

    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            consider("multiply", a, b)
        for b in sources:
            if b != a:
                consider("subtract", a, b)
    # On a tie prefer a product of two source columns (cost = quantity x unit_cost) over a difference that
    # leans on other derived columns (cost = revenue - margin): it is the more natural, more robust formula.
    out.sort(key=lambda c: (-c["match_ratio"], -c["recoverable"], c["op"] != "multiply", c["label"]))
    return out[:3]


# --------------------------------------------------------------------------- #
# Mappings
# --------------------------------------------------------------------------- #
def _mapping_series(df: pd.DataFrame, target: str, key: str) -> pd.Series | None:
    """key value -> target value, or None when the relationship is ambiguous or unproven."""
    k, t = df[key], df[target]
    have = k.notna() & t.notna()
    if int(have.sum()) < 2:
        return None
    pairs = pd.DataFrame({"k": k[have], "t": t[have]}).drop_duplicates()
    if pairs["k"].duplicated().any():          # one key value points at two different targets
        return None
    if int(have.sum()) == len(pairs):          # every key value seen once: nothing shows the link is stable
        return None
    return pairs.set_index("k")["t"]


def find_mapping_candidates(df: pd.DataFrame, target: str, key_cols: list[str], limit: int = 3) -> list[dict]:
    missing = df[target].isna()
    total_missing = int(missing.sum())
    if total_missing == 0 or total_missing == len(df):
        return []
    usable = []
    for key in key_cols:
        if key == target:
            continue
        reachable = int((missing & df[key].notna()).sum())
        if reachable:
            usable.append((df[key].nunique(), key))
    usable.sort()
    out = []
    for _, key in usable[:MAX_KEY_COLS]:
        mapping = _mapping_series(df, target, key)
        if mapping is None:
            continue
        n = int((missing & df[key].isin(mapping.index)).sum())
        if n:
            out.append({"key": key, "recoverable": n, "total_missing": total_missing})
    out.sort(key=lambda c: (-c["recoverable"], c["key"]))
    return out[:limit]


def mapping_fill(df: pd.DataFrame, target: str, key: str) -> pd.Series:
    """Values for the rows where `target` is missing and the mapping gives one answer (others NaN)."""
    mapping = _mapping_series(df, target, key)
    if mapping is None:
        return pd.Series(np.nan, index=df.index, dtype=object)
    lookup = mapping.to_dict()
    out = df[key].map(lookup).astype(object)
    return out.where(df[target].isna())

"""Step 2B - text standardisation, chosen per column and always optional.

Fixed order for every column (this is also what the Learn page tells the user):
    1. trim leading/trailing whitespace
    2. collapse repeated spaces
    3. change case (preserve / lower / UPPER / Title)
    4. find and replace (rules run top to bottom, matching the exact text, never a pattern)

Only text and category columns are accepted (validation.py enforces it). Identifier, number and date columns
never reach this module, so leading zeros and ID spellings cannot be touched.
"""
from __future__ import annotations

import re

import pandas as pd

from .errors import CleanSheetError
from .validation import TEXT_KINDS, is_locked

_REPEATED_SPACE = re.compile(r"[^\S\r\n]{2,}")                    # 2+ spaces/tabs in a row (not line breaks)
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")                 # letters, keeping apostrophes inside a word

CASE_LABELS = {"preserve": "Keep case", "lower": "lowercase", "upper": "UPPERCASE", "title": "Title Case"}


def title_case(text: str) -> str:
    """'don't PANIC' -> "Don't Panic". (str.title() would give "Don'T Panic".)"""
    return _WORD.sub(lambda m: m.group(0).capitalize(), text)


def _per_text_cell(s: pd.Series, fn) -> pd.Series:
    """Apply `fn` to every non-missing cell as text. Missing cells are left alone."""
    out = s.copy()
    have = s.dropna()
    if not have.empty:
        out.loc[have.index] = have.astype(str).map(fn)
    return out


def _replace_rule(s: pd.Series, rule: dict) -> pd.Series:
    find, repl = rule["find"], rule["replace"]
    if rule["whole_cell"]:
        if rule["match_case"]:
            return _per_text_cell(s, lambda t: repl if t == find else t)
        folded = find.lower()
        return _per_text_cell(s, lambda t: repl if t.lower() == folded else t)
    pattern = re.compile(re.escape(find), 0 if rule["match_case"] else re.IGNORECASE)
    return _per_text_cell(s, lambda t: pattern.sub(lambda _m: repl, t))   # callable: no backslash surprises


def standardise_series(s: pd.Series, step: dict) -> tuple[pd.Series, int]:
    """Run one column's steps. Returns (new series, cells that became empty and are now counted as missing)."""
    out = s
    if step["trim"]:
        out = _per_text_cell(out, str.strip)
    if step["collapse"]:
        out = _per_text_cell(out, lambda t: _REPEATED_SPACE.sub(" ", t))
    if step["case"] == "lower":
        out = _per_text_cell(out, str.lower)
    elif step["case"] == "upper":
        out = _per_text_cell(out, str.upper)
    elif step["case"] == "title":
        out = _per_text_cell(out, title_case)
    for rule in step["replace"]:
        out = _replace_rule(out, rule)
    emptied = out.notna() & out.astype(str).str.strip().eq("")
    if emptied.any():
        out = out.mask(emptied)          # a cell that ends up empty is missing, not an invisible blank string
    return out, int(emptied.sum())


def describe_columns(df: pd.DataFrame, profiles: list[dict]) -> list[dict]:
    """The columns the Text tab offers: text and category columns only (never IDs, numbers or dates)."""
    out = []
    for p in profiles:
        if p["kind"] not in TEXT_KINDS or is_locked(p) or p["non_missing"] == 0:
            continue
        s = df[p["name"]].dropna().astype(str)
        out.append({
            "name": p["name"], "kind": p["kind"], "kind_label": p["kind_label"], "sample": p["sample"],
            "unique": p["unique"],
            "edge_space": int((s != s.str.strip()).sum()),
            "repeated_space": int(s.str.contains(_REPEATED_SPACE).sum()),
            "mixed_case": bool(s.str.lower().nunique() < s.nunique()),
        })
    return out


def describe(step: dict) -> str:
    parts = []
    if step["trim"]:
        parts.append("trim spaces")
    if step["collapse"]:
        parts.append("collapse repeated spaces")
    if step["case"] != "preserve":
        parts.append(f"case: {CASE_LABELS[step['case']]}")
    if step["replace"]:
        n = len(step["replace"])
        parts.append(f"{n} find/replace rule{'s' if n != 1 else ''}")
    return ", ".join(parts)


def apply_text(df: pd.DataFrame, plan: dict[str, dict]) -> tuple[pd.DataFrame, dict]:
    """Apply a validated text plan to `df` (not modified). Returns (new frame, report)."""
    if not plan:
        return df, {"columns": [], "cells_changed": 0, "warnings": []}
    result = df.copy()
    entries, warnings = [], []
    total_changed = 0
    for col, step in plan.items():
        before = df[col]
        after, emptied = standardise_series(before, step)
        # post-conditions: same length, no cell came back from missing, only text cells were touched
        if len(after) != len(before) or bool((before.isna() & after.notna()).any()):
            raise CleanSheetError("A text change failed its consistency check, so nothing was applied.", 500,
                                  "consistency")
        changed = int((before.notna() & ((before != after) | after.isna())).sum())
        result[col] = after
        entry = {"column": col, "status": "applied", "label": describe(step), "changed": changed,
                 "became_empty": emptied, "warnings": []}
        if emptied:
            entry["warnings"].append(f"{emptied} cell(s) ended up empty and are now counted as missing.")
        warnings += [f"{col}: {w}" for w in entry["warnings"]]
        total_changed += changed
        entries.append(entry)
    return result, {"columns": entries, "cells_changed": total_changed, "warnings": warnings}

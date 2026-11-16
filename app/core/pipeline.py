"""Step 2 orchestration: validate the user's plan, then run missing values -> text -> data types.

`run_advanced` is a pure function of (basic-cleaned frame, plan). It never reads a previous result, so pressing
Apply twice, or going back and forth between steps, can never stack a change on top of an earlier run.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from .convert import apply_conversions
from .errors import CleanSheetError
from .missing import apply_missing
from .text import apply_text
from .validation import (validate_conversion_plan, validate_date_formats, validate_missing_plan,
                         validate_overrides, validate_text_plan)

ProfileFn = Callable[[dict, dict], list]       # (overrides, date_formats) -> list of column profiles


def _fail(message: str) -> None:
    raise CleanSheetError(message, 422, "invalid_selection")


def _dict_of_dicts(value, label: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, dict) for k, v in value.items()):
        _fail(f"The {label} selections were not understood.")
    return value


def _check_shape(raw) -> None:
    """Reject malformed JSON shapes with a clear 422 before the detailed validators run."""
    if not isinstance(raw, dict):
        _fail("The selections were not understood.")
    for key in ("types", "date_orders"):
        v = raw.get(key)
        if v is not None and not (isinstance(v, dict) and all(isinstance(a, str) and isinstance(b, str)
                                                              for a, b in v.items())):
            _fail("The column-type selections were not understood.")
    _dict_of_dicts(raw.get("missing"), "missing-value")
    for col, step in _dict_of_dicts(raw.get("text"), "text").items():
        rules = step.get("replace")
        if rules is not None and not (isinstance(rules, list) and all(isinstance(r, dict) for r in rules)):
            _fail(f"The find/replace rules for '{col}' were not understood.")
    _dict_of_dicts(raw.get("convert"), "data-type")
    for col, step in _dict_of_dicts(raw.get("missing"), "missing-value").items():
        if step.get("formula") is not None and not isinstance(step["formula"], dict):
            _fail(f"The formula choice for '{col}' was not understood.")


def parse_plan(raw, df: pd.DataFrame, profile_fn: ProfileFn) -> tuple[dict, dict[str, dict]]:
    """Validate everything the browser sent. Returns (clean plan, profiles by column name)."""
    _check_shape(raw)
    overrides = validate_overrides(raw.get("types"), df)
    date_formats = validate_date_formats(raw.get("date_orders"), df)
    profiles = {p["name"]: p for p in profile_fn(overrides, date_formats)}
    plan = {
        "types": overrides,
        "date_orders": date_formats,
        "missing": validate_missing_plan(raw.get("missing"), df, profiles),
        "text": validate_text_plan(raw.get("text"), df, profiles),
        "convert": validate_conversion_plan(raw.get("convert"), df, profiles),
    }
    return plan, profiles


def _changed_columns(before: pd.DataFrame, after: pd.DataFrame) -> list[str]:
    """Columns whose values differ between the two frames, comparing only rows present in both."""
    kept = before.loc[after.index]
    out = []
    for c in after.columns:
        a, b = kept[c], after[c]
        if bool((~((a == b) | (a.isna() & b.isna()))).any()):
            out.append(c)
    return out


def _operations(mrep: dict, trep: dict, crep: dict) -> list[dict]:
    ops: list[dict] = []
    for e in mrep["columns"]:
        if e["action"] == "remove":
            detail = f"Rows with a missing value here were removed ({e['rows_removed']} row(s) had one)."
        elif e["status"] == "skipped":
            detail = "Not applied."
        elif e["action"] == "formula":
            detail = f"Calculated {e['filled']} value(s): {e['fill_value']}."
        elif e["action"] == "mapping":
            detail = f"Filled {e['filled']} cell(s) {e['fill_value']}."      # fill_value reads "from 'column'"
        else:
            detail = f"Filled {e['filled']} cell(s) with {e['fill_value']}."
        ops.append({"step": "missing", "column": e["column"], "label": e["label"], "status": e["status"],
                    "detail": detail, "warnings": e["warnings"]})
    for e in trep["columns"]:
        ops.append({"step": "text", "column": e["column"], "label": e["label"], "status": e["status"],
                    "detail": f"{e['changed']} cell(s) changed.", "warnings": e["warnings"]})
    for e in crep["columns"]:
        detail = (f"Converted to {e['detail']}; {e['changed']} cell(s) rewritten."
                  if e["status"] == "applied" else "Not applied; original values kept.")
        ops.append({"step": "convert", "column": e["column"], "label": e["label"], "status": e["status"],
                    "detail": detail, "warnings": e["warnings"]})
    return ops


def run_advanced(basic: pd.DataFrame, plan: dict, profiles: dict[str, dict], basic_report: dict
                 ) -> tuple[pd.DataFrame, dict, dict[str, dict]]:
    """Run a validated plan on the basic-cleaned frame. Returns (final frame, report, xlsx column specs)."""
    df1, mrep = apply_missing(basic, profiles, plan["missing"])
    df2, trep = apply_text(df1, plan["text"])
    df3, crep, specs = apply_conversions(df2, profiles, plan["convert"])

    if list(df3.columns) != list(basic.columns) or not bool(df3.index.isin(basic.index).all()) \
            or not df3.index.is_unique:
        raise CleanSheetError("The result failed a consistency check, so nothing was applied.", 500, "consistency")

    changed = _changed_columns(basic, df3)
    converted = [e["column"] for e in crep["columns"] if e["status"] == "applied"]
    modified = [c for c in basic.columns if c in set(changed) | set(converted)]
    operations = _operations(mrep, trep, crep)
    warnings = mrep["warnings"] + trep["warnings"] + crep["warnings"]
    skipped = sum(1 for o in operations if o["status"] == "skipped")

    report = {
        "empty_plan": not (plan["missing"] or plan["text"] or plan["convert"]),
        "rows_original": basic_report["original_rows"],
        "rows_basic": int(len(basic)),
        "rows_final": int(len(df3)),
        "missing_original": basic_report["missing_before"],
        "missing_basic": int(basic.isna().sum().sum()),
        "missing_final": int(df3.isna().sum().sum()),
        "duplicates_removed": basic_report["duplicates_removed"],
        "rows_removed": mrep["rows_removed"],
        "cells_filled": mrep["cells_filled"],
        "text_cells_changed": trep["cells_changed"],
        "columns_total": int(df3.shape[1]),
        "columns_modified": len(modified),
        "modified_columns": modified,
        "conversions_completed": crep["completed"],
        "conversions_skipped": crep["skipped"],
        "operations_skipped": skipped,
        "operations": operations,
        "warnings": warnings,
    }
    return df3, report, specs

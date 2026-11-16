"""CSV and XLSX output, built in memory (no temporary files).

CSV: UTF-8 with a byte-order mark so Excel shows accented characters correctly; empty cells stay empty.
XLSX: columns are written with the type CleanSheet decided on, and nothing is ever treated as a formula:
  * number columns   - only when every value is a plain, canonical number (no leading zeros, <= 15 digits)
  * date columns     - only columns the user converted with "Date (YYYY-MM-DD)"
  * everything else  - text, so identifiers keep their leading zeros and their exact spelling
"""
from __future__ import annotations

import datetime as dt
import io
import re
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font

from .. import config
from .values import is_canonical_number, max_decimals, to_numbers

CSV_MIME = "text/csv; charset=utf-8"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NUMERIC_KINDS = ("numeric", "calculated")


# --------------------------------------------------------------------------- #
# Column specs
# --------------------------------------------------------------------------- #
def build_specs(df: pd.DataFrame, profiles: list[dict], conversions: dict[str, dict] | None = None
                ) -> dict[str, dict]:
    """How each column is written to .xlsx. `conversions` (from the user's data-type step) wins."""
    conversions = conversions or {}
    kinds = {p["name"]: p["kind"] for p in profiles}
    specs: dict[str, dict] = {}
    for c in df.columns:
        if c in conversions:
            specs[c] = conversions[c]
            continue
        spec = {"type": "text", "decimals": 0}
        if kinds.get(c) in NUMERIC_KINDS:
            values = df[c].dropna().astype(str).unique()
            if len(values) and all(is_canonical_number(v) for v in values):
                spec = {"type": "number", "decimals": min(config.MAX_DECIMAL_PLACES, max_decimals(df[c]))}
        specs[c] = spec
    return specs


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def csv_bytes(df: pd.DataFrame) -> bytes:
    text = df.to_csv(index=False, na_rep="", lineterminator="\r\n")
    return ("﻿" + text).encode("utf-8")


# --------------------------------------------------------------------------- #
# XLSX
# --------------------------------------------------------------------------- #
def _column_cells(ws, series: pd.Series, spec: dict) -> list:
    """Python values (or styled cells) for one column, in row order."""
    kind = spec["type"]
    if kind == "number" and not all(is_canonical_number(v) for v in series.dropna().astype(str).unique()):
        kind = "text"        # e.g. 16+ digit values would lose digits as an Excel number, so keep them exact
    if kind == "number":
        nums = to_numbers(series)
        places = spec["decimals"]
        fmt = "0" if places == 0 else "0." + "0" * places
        out: list = []
        for v in nums:
            if v != v:
                out.append(None)
            elif places == 0:
                out.append(int(v))
            else:
                cell = WriteOnlyCell(ws, value=float(v))
                cell.number_format = fmt
                out.append(cell)
        return out
    if kind == "date":
        parsed = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
        out = []
        for v in parsed:
            if pd.isna(v):
                out.append(None)
            else:
                cell = WriteOnlyCell(ws, value=v.to_pydatetime())
                cell.number_format = "yyyy-mm-dd"
                out.append(cell)
        return out
    out = []
    for v in series:
        if v is None or (isinstance(v, float) and v != v):
            out.append(None)
            continue
        text = ILLEGAL_CHARACTERS_RE.sub("", str(v))
        if text.startswith("="):                    # keep it text: never let a cell turn into a formula
            cell = WriteOnlyCell(ws, value=text)
            cell.data_type = "s"
            out.append(cell)
        else:
            out.append(text)
    return out


def xlsx_bytes(df: pd.DataFrame, specs: dict[str, dict]) -> bytes:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Cleaned data")
    for i, name in enumerate(df.columns, start=1):
        sample = df[name].dropna().astype(str).head(200)
        width = max([len(str(name))] + [len(v) for v in sample]) + 2
        ws.column_dimensions[_col_letter(i)].width = min(max(width, 8), 50)
    ws.freeze_panes = "A2"
    bold = Font(bold=True)
    header = []
    for name in df.columns:
        cell = WriteOnlyCell(ws, value=ILLEGAL_CHARACTERS_RE.sub("", str(name)))
        cell.data_type = "s"
        cell.font = bold
        header.append(cell)
    ws.append(header)
    columns = [_column_cells(ws, df[name], specs.get(name, {"type": "text", "decimals": 0})) for name in df.columns]
    for row in zip(*columns):
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _col_letter(n: int) -> str:
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


# --------------------------------------------------------------------------- #
# Download names
# --------------------------------------------------------------------------- #
def download_name(display_name: str, stage: str, fmt: str) -> str:
    stem = Path(display_name).stem or "data"
    suffix = {"basic": "basic_cleaned", "final": "cleaned"}[stage]
    return f"{stem}_{suffix}.{fmt}"


def content_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"

"""Small builders used across the tests (kept out of conftest so they can be imported by name)."""
from __future__ import annotations

import csv
import io
from urllib.parse import quote

import pandas as pd
from openpyxl import Workbook

from app.core import pipeline
from app.core.profiling import profile_frame


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #
def csv_bytes(header, rows, delimiter=",", encoding="utf-8") -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([["" if v is None else v for v in row] for row in rows])
    return buf.getvalue().encode(encoding)


def xlsx_bytes(header, rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def xlsx_with_dimension(header, rows, ref: str) -> bytes:
    """A valid workbook whose sheet declares `ref` (e.g. "A1:XFD50") as its used range, the way Excel records it
    when whole columns or rows were formatted."""
    import re
    import zipfile

    src = zipfile.ZipFile(io.BytesIO(xlsx_bytes(header, rows)))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = re.sub(rb'<dimension ref="[^"]*"', b'<dimension ref="%s"' % ref.encode(), data)
            dst.writestr(item, data)
    return out.getvalue()


def upload(client, data: bytes, name: str = "data.csv"):
    return client.post("/api/upload", content=data,
                       headers={"X-Filename": quote(name), "Content-Type": "application/octet-stream"})


def api_ok(response) -> dict:
    """The JSON body of a response that must have succeeded (the failure message is shown if it did not)."""
    assert response.status_code == 200, f"{response.status_code}: {response.text[:300]}"
    return response.json()


def basic_options(**changes) -> dict:
    """Step 1 options with every cleaning switched on (override with keyword arguments)."""
    opts = {"remove_duplicates": True, "dedupe_mode": "all", "dedupe_columns": [], "trim": True,
            "normalise_missing": True, "binary": {}}
    opts.update(changes)
    return opts


# --------------------------------------------------------------------------- #
# Frames (the same shape the app uses: every cell is text, missing is None/NaN)
# --------------------------------------------------------------------------- #
def frame(**cols) -> pd.DataFrame:
    return pd.DataFrame({k: pd.Series(v, dtype=object) for k, v in cols.items()})


def profiles_of(df: pd.DataFrame, overrides=None, date_formats=None) -> dict[str, dict]:
    return {p["name"]: p for p in profile_frame(df, overrides or {}, True, date_formats or {})}


def run_advanced(df: pd.DataFrame, raw_plan: dict):
    """Validate and run an advanced plan exactly like the API does. Returns (final, report, xlsx specs)."""
    def profile_fn(overrides, date_formats):
        return profile_frame(df, overrides, True, date_formats)

    plan, profiles = pipeline.parse_plan(raw_plan, df, profile_fn)
    basic_report = {"original_rows": len(df), "missing_before": int(df.isna().sum().sum()),
                    "duplicates_removed": 0}
    return pipeline.run_advanced(df, plan, profiles, basic_report)


def values(series: pd.Series) -> list:
    """Series as a plain list with missing shown as None (easy to compare in assertions)."""
    return [None if pd.isna(v) else v for v in series]

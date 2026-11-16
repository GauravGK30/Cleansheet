"""Workbooks with formulas: results saved by Excel are read; formulas with no saved result are reported, not hidden."""
from __future__ import annotations

import io
import re
import zipfile

import pytest
from helpers import api_ok, upload
from openpyxl import Workbook

from app.core import files


def workbook(saved_results: bool, rows: int = 5, other_sheet: bool = False) -> bytes:
    """qty, price, total (= qty x price as a formula). With `saved_results` the sheet also stores each formula's
    last result the way Excel does; without it (how scripts and libraries write files) it does not."""
    wb = Workbook()
    ws = wb.active
    ws.append(["qty", "price", "total", "note"])
    for i in range(1, rows + 1):
        ws.append([i, 2.5, f"=A{i + 1}*B{i + 1}", "x"])
    if other_sheet:
        wb.create_sheet("Other").append(["=1+1"])
    buf = io.BytesIO()
    wb.save(buf)
    if not saved_results:
        return buf.getvalue()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                text = re.sub(r'(<c r="C(\d+)"[^>]*><f>[^<]*</f>)<v\s*/>|(<c r="C(\d+)"[^>]*><f>[^<]*</f>)<v></v>',
                              lambda m: (m.group(1) or m.group(3)) + f"<v>{(int(m.group(2) or m.group(4)) - 1) * 2.5}</v>",
                              data.decode())
                data = text.encode()
            dst.writestr(item, data)
    return out.getvalue()


def load(data: bytes):
    return files.load_upload(io.BytesIO(data), "book.xlsx")


def test_formulas_with_saved_results_load_as_those_results_without_any_warning():
    got = load(workbook(saved_results=True))
    assert got.df["total"].tolist() == ["2.5", "5", "7.5", "10", "12.5"]
    assert got.warnings == []


def test_formulas_with_no_saved_result_are_reported_with_the_column_and_count():
    got = load(workbook(saved_results=False))
    assert got.df["total"].isna().all()
    assert len(got.warnings) == 1
    w = got.warnings[0]
    assert "5 formula cell(s)" in w and "'total'" in w and "no saved result" in w and "save it" in w


def test_plain_workbooks_and_csv_files_have_no_warnings():
    wb = Workbook()
    wb.active.append(["a", "b"])
    wb.active.append([1, 2])
    buf = io.BytesIO()
    wb.save(buf)
    assert load(buf.getvalue()).warnings == []
    assert files.load_upload(io.BytesIO(b"a,b\n1,2\n"), "x.csv").warnings == []


def test_a_formula_on_a_sheet_that_is_not_loaded_does_not_trigger_a_warning():
    got = load(workbook(saved_results=True, other_sheet=True))
    assert got.warnings == []


def test_the_warning_lists_at_most_five_columns():
    wb = Workbook()
    ws = wb.active
    ws.append(["id"] + [f"c{i}" for i in range(8)])
    ws.append(["row1"] + [f"=1+{i}" for i in range(8)])
    buf = io.BytesIO()
    wb.save(buf)
    w = load(buf.getvalue()).warnings[0]
    assert "8 formula cell(s) in 8 column(s)" in w and w.count("'c") == 5 and "…" in w


def test_a_sheet_that_is_only_unsaved_formulas_says_why_it_is_empty():
    wb = Workbook()
    ws = wb.active
    ws.append(["a", "b"])
    ws.append(["=1+1", "=2+2"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(files.CleanSheetError) as err:
        load(buf.getvalue())
    assert err.value.code == "unsaved_formulas" and "no saved result" in err.value.message


def test_the_api_passes_the_warning_to_the_page_and_still_loads_the_file(client):
    body = api_ok(upload(client, workbook(saved_results=False), "book.xlsx"))
    assert body["rows"] == 5 and len(body["load_warnings"]) == 1
    assert client.get("/api/state").json()["load_warnings"] == body["load_warnings"]
    csv_body = api_ok(upload(client, b"a,b\n1,2\n", "ok.csv"))
    assert csv_body["load_warnings"] == []


def test_a_failure_in_the_formula_check_never_blocks_the_upload(monkeypatch):
    def boom(_path):
        raise RuntimeError("check failed")

    monkeypatch.setattr(files, "_workbook_has_formulas", boom)
    got = load(workbook(saved_results=False))
    assert got.warnings == [] and len(got.df) == 5

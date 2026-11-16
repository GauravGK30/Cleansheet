"""CSV and XLSX export: what is actually written into the files people download."""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd
import pytest
from helpers import frame, profiles_of
from openpyxl import load_workbook

from app.core import export


def read_xlsx(df: pd.DataFrame, specs: dict | None = None):
    data = export.xlsx_bytes(df, specs or export.build_specs(df, list(profiles_of(df).values())))
    return load_workbook(io.BytesIO(data)).active


def cells(ws, column: int) -> list:
    return [ws.cell(row=r, column=column) for r in range(2, ws.max_row + 1)]


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def test_csv_has_a_byte_order_mark_so_excel_shows_accents_and_uses_crlf():
    raw = export.csv_bytes(frame(name=["José", "Zoë"], n=["1", "2"]))
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw and "José" in raw.decode("utf-8-sig")


def test_csv_round_trips_awkward_cells_exactly():
    original = frame(a=["x,y", 'say "hi"', "two\nlines", " padded ", "00123", None],
                     b=["1", "2", "3", "4", "5", "6"])
    back = pd.read_csv(io.BytesIO(export.csv_bytes(original)), dtype=str, keep_default_na=False,
                       encoding="utf-8-sig").replace({"": None})
    assert back["a"].tolist() == original["a"].tolist()          # commas, quotes, line breaks, leading zeros, gaps


def test_missing_cells_are_written_empty_never_as_nan_or_none():
    text = export.csv_bytes(frame(a=["1", None], b=[None, "2"])).decode("utf-8-sig")
    assert "nan" not in text.lower() and "none" not in text.lower()
    assert text.splitlines()[1:] == ["1,", ",2"]


# --------------------------------------------------------------------------- #
# XLSX
# --------------------------------------------------------------------------- #
def test_xlsx_has_a_bold_header_a_frozen_row_and_the_right_shape():
    ws = read_xlsx(frame(a=["1", "2"], b=["x", "y"]))
    assert [c.value for c in ws[1]] == ["a", "b"] and all(c.font.bold for c in ws[1])
    assert ws.freeze_panes == "A2" and ws.max_row == 3 and ws.title == "Cleaned data"


def test_identifiers_stay_text_with_their_leading_zeros():
    df = frame(customer_id=["00123", "00456", "00789"], name=["Ann", "Bo", "Cy"])
    ws = read_xlsx(df)
    ids = cells(ws, 1)
    assert [c.value for c in ids] == ["00123", "00456", "00789"] and all(c.data_type == "s" for c in ids)


def test_number_columns_are_real_numbers_with_a_matching_display_format():
    df = frame(qty=["1", "2", "3"], price=["2.50", "10.00", "7.25"], customer_id=["00001", "00002", "00003"],
               amount=["10", "20", "30"])
    ws = read_xlsx(df, {"qty": {"type": "number", "decimals": 0}, "price": {"type": "number", "decimals": 2},
                        "customer_id": {"type": "text", "decimals": 0}, "amount": {"type": "number", "decimals": 0}})
    assert [c.value for c in cells(ws, 1)] == [1, 2, 3] and all(c.data_type == "n" for c in cells(ws, 1))
    assert [c.value for c in cells(ws, 2)] == [2.5, 10.0, 7.25]
    assert {c.number_format for c in cells(ws, 2)} == {"0.00"}
    assert cells(ws, 3)[0].data_type == "s"


def test_converted_date_columns_become_real_excel_dates():
    df = frame(when=["2024-03-05", None, "2024-12-31"])
    ws = read_xlsx(df, {"when": {"type": "date", "decimals": 0}})
    got = cells(ws, 1)
    assert got[0].value == dt.datetime(2024, 3, 5) and got[0].number_format == "yyyy-mm-dd"
    assert got[1].value is None and got[2].value == dt.datetime(2024, 12, 31)


def test_text_that_looks_like_a_formula_is_never_turned_into_one():
    df = frame(note=["=SUM(A1:A9)", "=1+1", "+1", "@x", "plain"])
    ws = read_xlsx(df, {"note": {"type": "text", "decimals": 0}})
    got = cells(ws, 1)
    assert got[0].value == "=SUM(A1:A9)" and got[0].data_type == "s"     # still a string, not a formula
    assert got[1].data_type == "s"


def test_numbers_too_long_for_excel_stay_exact_as_text():
    big = "12345678901234567890"                                   # 20 digits: a double would silently round it
    ws = read_xlsx(frame(n=[big, "1"]), {"n": {"type": "number", "decimals": 0}})
    assert cells(ws, 1)[0].value == big


def test_missing_cells_are_empty_in_xlsx_and_control_characters_are_removed():
    ws = read_xlsx(frame(a=["ok\x07bell", None, "fine"]))
    got = [c.value for c in cells(ws, 1)]
    assert got == ["okbell", None, "fine"]


def test_unconverted_numeric_columns_with_leading_zeros_are_not_turned_into_numbers():
    df = frame(zip_code=["01234", "02345", "10001"], qty=["1", "2", "3"])
    specs = export.build_specs(df, list(profiles_of(df).values()))
    assert specs["zip_code"]["type"] == "text"


def test_a_user_conversion_overrides_the_automatic_spec():
    df = frame(a=["1", "2"])
    specs = export.build_specs(df, list(profiles_of(df).values()), {"a": {"type": "text", "decimals": 0}})
    assert specs["a"]["type"] == "text"


def test_xlsx_has_exactly_the_rows_and_columns_of_the_dataframe():
    df = frame(**{f"c{i}": [str(i * j) for j in range(40)] for i in range(7)})
    ws = read_xlsx(df)
    assert (ws.max_row, ws.max_column) == (41, 7)


# --------------------------------------------------------------------------- #
# Download names and headers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("stage, fmt, expected", [("basic", "csv", "orders_basic_cleaned.csv"),
                                                  ("final", "xlsx", "orders_cleaned.xlsx")])
def test_download_names_say_what_the_file_is(stage, fmt, expected):
    assert export.download_name("orders.csv", stage, fmt) == expected


def test_content_disposition_cannot_be_used_to_inject_headers():
    header = export.content_disposition('evil"\r\nSet-Cookie: x=1.csv')
    assert "\r" not in header and "\n" not in header
    assert header.startswith("attachment;") and 'filename="' in header
    assert "filename*=UTF-8''" in export.content_disposition("résumé.csv")

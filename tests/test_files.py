"""File handling: loading CSV and XLSX, content validation, size/shape limits, and safe temporary files."""
from __future__ import annotations

import io
import os
import re
import time
import zipfile
from pathlib import Path

import pytest

from app import config
from app.core import files
from app.core.errors import CleanSheetError
from helpers import csv_bytes, xlsx_bytes, xlsx_with_dimension


def load(data: bytes, name: str = "data.csv"):
    return files.load_upload(io.BytesIO(data), name)


def code_of(data: bytes, name: str) -> str:
    with pytest.raises(CleanSheetError) as err:
        load(data, name)
    return err.value.code


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def test_csv_cells_load_as_text_so_leading_zeros_survive_and_blanks_are_missing():
    got = load(csv_bytes(["id", "qty", "note"], [["00106", "7", None], ["2", " ", "x"]]))
    df = got.df
    assert list(df.columns) == ["id", "qty", "note"]
    assert df.loc[0, "id"] == "00106"                       # not 106
    assert df["note"].isna().tolist() == [True, False]      # empty cell -> missing
    assert df.loc[1, "qty"] == " "                          # a space is data until Step 1 trims it
    assert got.fmt == "csv" and got.notes == []


def test_csv_byte_order_mark_is_not_part_of_the_first_header():
    df = load("﻿id,name\n1,a\n".encode("utf-8")).df
    assert list(df.columns) == ["id", "name"]


@pytest.mark.parametrize("delimiter,word", [(";", "semicolon"), ("\t", "tab"), ("|", "pipe")])
def test_csv_separator_is_detected_and_reported(delimiter, word):
    got = load(csv_bytes(["a", "b"], [["1", "2"]], delimiter=delimiter))
    assert list(got.df.columns) == ["a", "b"]
    assert any(word in n for n in got.notes)


def test_csv_in_windows_1252_is_read_correctly_and_reported():
    got = load(csv_bytes(["name"], [["Café"]], encoding="cp1252"))
    assert got.df.loc[0, "name"] == "Café"
    assert any("Windows-1252" in n for n in got.notes)


def test_csv_quoted_commas_quotes_and_line_breaks_stay_inside_their_cell():
    got = load(csv_bytes(["id", "note"], [["1", "a, b"], ["2", 'say "hi"'], ["3", "line1\nline2"]]))
    assert got.df["note"].tolist() == ["a, b", 'say "hi"', "line1\nline2"]


def test_csv_short_rows_are_padded_with_missing_and_blank_lines_are_skipped():
    got = load(b"a,b,c\n1,2\n\n3,4,5\n")
    assert len(got.df) == 2
    assert got.df.loc[0, "c"] is None or got.df["c"].isna().iloc[0]


def test_csv_rows_longer_than_the_header_are_refused_with_a_clear_message():
    assert code_of(b"a,b\n1,2,3\n", "x.csv") == "bad_csv"


def test_blank_and_duplicate_headers_are_made_usable_and_reported():
    got = load(b" a ,a,,b\n1,2,3,4\n")
    assert list(got.df.columns) == ["a", "a (2)", "Column 3", "b"]
    assert len(got.notes) == 2


def test_extension_is_case_insensitive():
    assert len(load(b"a\n1\n", "DATA.CSV").df) == 1


# --------------------------------------------------------------------------- #
# XLSX
# --------------------------------------------------------------------------- #
def test_xlsx_values_become_clean_text():
    import datetime as dt
    rows = [["00106", 5, 5.0, 2.5, True, dt.date(2024, 3, 1), dt.datetime(2024, 3, 1, 13, 30), None]]
    got = load(xlsx_bytes(list("abcdefgh"), rows), "book.xlsx")
    assert got.fmt == "xlsx"
    assert got.df.iloc[0].tolist()[:7] == ["00106", "5", "5", "2.5", "TRUE", "2024-03-01", "2024-03-01 13:30:00"]
    assert got.df["h"].isna().iloc[0] or len(got.df.columns) == 7


def test_xlsx_numeric_header_and_trailing_empty_columns():
    got = load(xlsx_bytes([2024, "b", None, None], [[1, 2, None, None]]), "book.xlsx")
    assert list(got.df.columns) == ["2024", "b"]


def test_xlsx_uses_the_first_sheet_with_data_and_says_so():
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "Empty"
    ws = wb.create_sheet("Orders")
    ws.append(["a", "b"])
    ws.append([1, 2])
    wb.create_sheet("Other").append(["z"])
    buf = io.BytesIO()
    wb.save(buf)
    got = load(buf.getvalue(), "book.xlsx")
    assert list(got.df.columns) == ["a", "b"]
    assert any("Orders" in n and "ignored" in n for n in got.notes)


def test_xlsx_blank_rows_are_skipped():
    got = load(xlsx_bytes(["a"], [[1], [None], [2]]), "book.xlsx")
    assert got.df["a"].tolist() == ["1", "2"]


def test_xlsx_with_an_inflated_declared_sheet_size_still_loads():
    """Regression: Excel records A1:XFD50 when whole columns are formatted. A 3-column sheet used to be
    rejected as 'more than 200 columns' (every row was padded to 16,384 cells)."""
    data = xlsx_with_dimension(["id", "name", "qty"], [["1", "a", 5], ["2", "b", 6]], "A1:XFD50")
    got = load(data, "book.xlsx")
    assert list(got.df.columns) == ["id", "name", "qty"]
    assert len(got.df) == 2


@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
def test_exactly_the_maximum_number_of_columns_loads_and_one_more_is_refused(fmt):
    def build(n):
        header = [f"c{i}" for i in range(n)]
        row = [str(i) for i in range(n)]
        return (csv_bytes(header, [row]) if fmt == "csv" else xlsx_bytes(header, [row])), f"w.{fmt}"
    data, name = build(config.MAX_COLS)
    assert load(data, name).df.shape[1] == config.MAX_COLS
    data, name = build(config.MAX_COLS + 1)
    assert code_of(data, name) == "too_many_columns"


# --------------------------------------------------------------------------- #
# Content validation: the extension is never trusted on its own
# --------------------------------------------------------------------------- #
def test_empty_and_data_less_files_are_refused_with_distinct_messages():
    assert code_of(b"", "a.csv") == "empty_file"
    assert code_of(b"   \n\n", "a.csv") == "empty_file"
    assert code_of(b"id,name\n", "a.csv") == "empty_file"                    # header but no rows
    assert code_of(xlsx_bytes(["a", "b"], []), "a.xlsx") == "empty_file"
    from openpyxl import Workbook
    buf = io.BytesIO()
    Workbook().save(buf)
    assert code_of(buf.getvalue(), "a.xlsx") == "empty_file"                 # a workbook with nothing in it


@pytest.mark.parametrize("name", ["a.txt", "a.xls", "a.xlsm", "a.json", "a", "a.csv.exe", ".csv.bak"])
def test_only_csv_and_xlsx_extensions_are_accepted(name):
    assert code_of(b"a,b\n1,2\n", name) == "bad_extension"


def test_an_excel_workbook_named_csv_is_recognised_by_its_content():
    assert code_of(xlsx_bytes(["a"], [[1]]), "a.csv") == "content_mismatch"


def test_text_named_xlsx_is_not_a_workbook():
    assert code_of(b"a,b\n1,2\n", "a.xlsx") == "invalid_spreadsheet"


def test_old_xls_and_password_protected_files_get_a_helpful_message():
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600
    assert code_of(ole, "a.xlsx") == "legacy_excel"
    assert code_of(ole, "a.csv") == "legacy_excel"


def test_utf16_and_binary_files_are_not_accepted_as_csv():
    assert code_of("a,b\n1,2\n".encode("utf-16"), "a.csv") == "not_text"
    assert code_of(b"a,b\n1,\x00\x01\x02\n", "a.csv") == "not_text"


def test_corrupt_or_foreign_zip_files_are_not_workbooks():
    good = xlsx_bytes(["a"], [[1]])
    assert code_of(good[: len(good) // 2], "a.xlsx") == "invalid_spreadsheet"   # truncated
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<x/>")
    assert code_of(buf.getvalue(), "a.xlsx") == "invalid_spreadsheet"          # a zip, but not a workbook


def test_zip_bombs_are_refused(monkeypatch):
    monkeypatch.setattr(config, "MAX_XLSX_UNCOMPRESSED_BYTES", 100)
    assert code_of(xlsx_bytes(["a"], [[1]]), "a.xlsx") == "zip_bomb"


# --------------------------------------------------------------------------- #
# Size and shape limits
# --------------------------------------------------------------------------- #
def test_the_upload_limit_is_one_constant_and_defaults_to_50_mb():
    assert config.MAX_UPLOAD_BYTES == config.MAX_UPLOAD_MB * 1024 * 1024
    if "CLEANSHEET_MAX_UPLOAD_MB" not in os.environ:
        assert config.MAX_UPLOAD_MB == 50
    assert config._int_env("CLEANSHEET_NO_SUCH_VARIABLE", 50) == 50


def test_environment_overrides_are_used_but_nonsense_falls_back(monkeypatch):
    monkeypatch.setenv("CLEANSHEET_TEST_LIMIT", "75")
    assert config._int_env("CLEANSHEET_TEST_LIMIT", 50) == 75
    for bad in ("abc", "-3", "0", "", "  "):
        monkeypatch.setenv("CLEANSHEET_TEST_LIMIT", bad)
        assert config._int_env("CLEANSHEET_TEST_LIMIT", 50) == 50


def test_save_stream_stops_at_the_size_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1000)
    with pytest.raises(CleanSheetError) as err:
        files.save_stream(io.BytesIO(b"x" * 5000), tmp_path / "out.bin")
    assert err.value.code == "too_large" and err.value.status == 413
    assert files.save_stream(io.BytesIO(b"x" * 1000), tmp_path / "ok.bin") == 1000     # exactly at the limit


@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
def test_row_limit_counts_data_rows_not_the_header(monkeypatch, fmt):
    monkeypatch.setattr(config, "MAX_ROWS", 3)
    def build(n):
        rows = [[str(i)] for i in range(n)]
        return csv_bytes(["a"], rows) if fmt == "csv" else xlsx_bytes(["a"], rows)
    assert len(load(build(3), f"a.{fmt}").df) == 3
    assert code_of(build(4), f"a.{fmt}") == "too_many_rows"


def test_cell_limit_protects_memory(monkeypatch):
    monkeypatch.setattr(config, "MAX_CELLS", 10)
    assert code_of(csv_bytes(["a", "b", "c"], [["1", "2", "3"]] * 4), "a.csv") == "too_many_cells"


# --------------------------------------------------------------------------- #
# Names and temporary files
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd.csv", "passwd.csv"),
    ("..\\..\\windows\\system32\\evil.xlsx", "evil.xlsx"),
    ("/abs/path/data.csv", "data.csv"),
    ("my file (1).csv", "my file _1_.csv"),
    ("", "upload"),
    (None, "upload"),
    ("résumé 中文.csv", "résumé 中文.csv"),
])
def test_display_names_are_stripped_of_paths_and_odd_characters(raw, expected):
    assert files.safe_display_name(raw) == expected


def test_display_names_are_length_limited_and_free_of_control_characters():
    name = files.safe_display_name("a" * 500 + ".csv")
    assert len(name) <= 100
    assert "\x00" not in files.safe_display_name("bad\x00name\r\n.csv")
    assert "\n" not in files.safe_display_name("bad\x00name\r\n.csv")


def test_temp_paths_are_unique_private_and_never_built_from_the_users_filename(tmp_path):
    seen = set()
    for _ in range(5):
        with files.temp_upload_path(".csv") as p:
            assert re.fullmatch(r"upload_[0-9a-f]{32}\.csv", p.name)
            assert p.parent == config.TEMP_DIR
            seen.add(p.name)
    assert len(seen) == 5
    if hasattr(os, "getuid"):
        assert (config.TEMP_DIR.stat().st_mode & 0o777) == 0o700


def test_the_temp_file_is_removed_after_a_successful_load_and_after_every_kind_of_failure(client):
    from helpers import upload
    good = csv_bytes(["a"], [["1"]])
    for data, name in [(good, "ok.csv"), (b"", "empty.csv"), (b"a,b\n1,2,3\n", "ragged.csv"),
                       (good, "wrong.txt"), (xlsx_bytes(["a"], [[1]]), "mismatch.csv"), (b"junk", "bad.xlsx")]:
        upload(client, data, name)
        assert list(config.TEMP_DIR.glob("upload_*")) == [], f"temp file left behind after {name}"


def test_the_temp_file_is_removed_when_the_upload_is_too_large_mid_stream(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1000)

    def chunks():                                   # a generator body: no Content-Length, so only the stream can tell
        yield b"a,b\n"
        for _ in range(50):
            yield b"1,2\n" * 10                     # 40 bytes per chunk: 2,000+ bytes in all, over the 1,000 limit

    r = client.post("/api/upload", content=chunks(), headers={"X-Filename": "big.csv"})
    assert r.status_code == 413
    assert r.json()["code"] == "too_large"
    assert list(config.TEMP_DIR.glob("upload_*")) == []


def test_stale_leftovers_are_purged_but_fresh_and_unrelated_files_are_kept():
    folder = files.ensure_temp_dir()
    old, fresh, other = folder / "upload_old.csv", folder / "upload_new.csv", folder / "notes.txt"
    for p in (old, fresh, other):
        p.write_text("x")
    long_ago = time.time() - config.STALE_TEMP_SECONDS - 60
    os.utime(old, (long_ago, long_ago))
    os.utime(other, (long_ago, long_ago))
    assert files.purge_stale_temp_files() == 1
    assert not old.exists() and fresh.exists() and other.exists()


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="ownership checks are POSIX-only")
def test_a_symlinked_temp_folder_is_never_used(tmp_path, monkeypatch):
    target = tmp_path / "attacker_dir"
    target.mkdir()
    link = tmp_path / "predictable_name"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(config, "TEMP_DIR", link)
    used = files.ensure_temp_dir()
    assert used != link and not used.is_symlink() and used.is_dir()
    assert config.TEMP_DIR == used                           # later calls keep using the safe folder
    with files.temp_upload_path(".csv") as p:
        assert p.parent == used and list(target.iterdir()) == []


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="ownership checks are POSIX-only")
def test_a_temp_folder_owned_by_someone_else_is_never_used(tmp_path, monkeypatch):
    shared = tmp_path / "cleansheet_tmp"
    shared.mkdir()
    monkeypatch.setattr(config, "TEMP_DIR", shared)
    monkeypatch.setattr(files.os, "getuid", lambda: os.stat(shared).st_uid + 1)    # pretend we are another user
    used = files.ensure_temp_dir()
    assert used != shared and used.is_dir()


def test_a_dangling_symlink_at_the_temp_path_does_not_break_uploads(tmp_path, monkeypatch):
    link = tmp_path / "dangling"
    link.symlink_to(tmp_path / "does_not_exist")
    monkeypatch.setattr(config, "TEMP_DIR", link)
    used = files.ensure_temp_dir()
    assert used.is_dir() and used != link

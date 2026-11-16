"""File handling: safe upload to a temp file, content validation, and loading into a DataFrame.

Everything is loaded as text (object dtype, missing cells are None) so identifiers, leading zeros and
exact spellings survive. Uploaded cell contents are never logged.
"""
from __future__ import annotations

import codecs
import csv
import datetime as dt
import logging
import os
import re
import stat
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path
from typing import Iterator

import pandas as pd

from .. import config
from .errors import CleanSheetError

log = logging.getLogger("cleansheet.files")

_CHUNK = 1024 * 1024
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"   # legacy .xls and password-protected Office files
_ZIP_MAGIC = b"PK\x03\x04"


@dataclass
class LoadedFile:
    df: pd.DataFrame
    filename: str                       # sanitised display name, never used as a path
    fmt: str                            # "csv" or "xlsx"
    notes: list[str] = field(default_factory=list)        # things worth knowing (separator, ignored sheets...)
    warnings: list[str] = field(default_factory=list)     # data may differ from what the person expects


# --------------------------------------------------------------------------- #
# Temp files
# --------------------------------------------------------------------------- #
def _is_ours(path: Path) -> bool:
    """On POSIX: a real directory (not a symlink) owned by the current user. Elsewhere: assume yes."""
    if not hasattr(os, "getuid"):
        return path.is_dir()
    try:
        st = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid()


def ensure_temp_dir() -> Path:
    """The private folder uploads are staged in (owner-only). The default path is predictable and lives in a
    shared temp folder, so a folder or symlink someone else created there is never used: a fresh private
    one is made instead."""
    d = config.TEMP_DIR
    try:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
    except FileExistsError:                       # e.g. a dangling symlink
        pass
    if not _is_ours(d):
        d = config.TEMP_DIR = Path(tempfile.mkdtemp(prefix="cleansheet_"))
        log.warning("the configured temporary folder is not private to this user; using a new one")
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def purge_stale_temp_files() -> int:
    """Delete leftover upload files (e.g. after a crash) older than the configured age."""
    removed = 0
    cutoff = time.time() - config.STALE_TEMP_SECONDS
    for p in ensure_temp_dir().glob("upload_*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            continue
    return removed


@contextmanager
def temp_upload_path(suffix: str) -> Iterator[Path]:
    """A unique path inside TEMP_DIR (never derived from the user's filename); removed on exit."""
    path = ensure_temp_dir() / f"upload_{uuid.uuid4().hex}{suffix}"
    try:
        yield path
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.warning("could not remove a temporary upload file")


def safe_display_name(filename: str | None) -> str:
    name = Path((filename or "").replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ]+", "_", name, flags=re.UNICODE).strip(" .")
    return (name or "upload")[:100]


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def save_stream(stream, dest: Path) -> int:
    """Copy an uploaded stream to `dest`, refusing anything over the size limit."""
    size = 0
    with open(dest, "wb") as out:
        while True:
            chunk = stream.read(_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                raise CleanSheetError(
                    f"The file is larger than the {config.MAX_UPLOAD_MB} MB limit.", 413, "too_large")
            out.write(chunk)
    return size


# --------------------------------------------------------------------------- #
# Content validation (the extension is never trusted on its own)
# --------------------------------------------------------------------------- #
def validate_content(path: Path, ext: str) -> str:
    """Check the bytes match the extension. Returns "csv" or "xlsx"."""
    if ext not in config.ALLOWED_EXTENSIONS:
        raise CleanSheetError("Only .csv and .xlsx files are supported.", 400, "bad_extension")
    size = path.stat().st_size
    if size == 0:
        raise CleanSheetError("The file is empty.", 400, "empty_file")
    with open(path, "rb") as fh:
        head = fh.read(8192)
    if head.startswith(_OLE_MAGIC):
        raise CleanSheetError(
            "This looks like an old .xls or a password-protected Excel file. "
            "Save it as a regular .xlsx (without a password) and upload it again.", 400, "legacy_excel")
    if ext == ".xlsx":
        if not head.startswith(_ZIP_MAGIC):
            raise CleanSheetError("This file is not a valid .xlsx workbook.", 400, "invalid_spreadsheet")
        _validate_xlsx_archive(path)
        return "xlsx"
    if head.startswith(_ZIP_MAGIC):
        raise CleanSheetError(
            "This file is an Excel workbook with a .csv name. Rename it to .xlsx and upload it again.",
            400, "content_mismatch")
    if b"\x00" in head or head.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise CleanSheetError(
            "This does not look like a text CSV file (it may be UTF-16 or binary). "
            "Save it as 'CSV UTF-8' and try again.", 400, "not_text")
    return "csv"


def _validate_xlsx_archive(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            names = {i.filename for i in infos}
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise CleanSheetError("This file is not a valid .xlsx workbook.", 400, "invalid_spreadsheet")
            if len(infos) > 5000 or sum(i.file_size for i in infos) > config.MAX_XLSX_UNCOMPRESSED_BYTES:
                raise CleanSheetError(
                    "This workbook expands to an unsafe size and was rejected.", 400, "zip_bomb")
    except zipfile.BadZipFile:
        raise CleanSheetError("This file is not a valid .xlsx workbook.", 400, "invalid_spreadsheet") from None


# --------------------------------------------------------------------------- #
# Headers and shape limits
# --------------------------------------------------------------------------- #
def clean_headers(raw: list) -> tuple[list[str], list[str]]:
    """Strip names, name blank headers, and make duplicates unique. Returns (names, notes)."""
    notes: list[str] = []
    names: list[str] = []
    seen: dict[str, int] = {}
    blank = renamed = 0
    for i, value in enumerate(raw):
        name = "" if value is None else str(value).strip()
        if not name:
            name = f"Column {i + 1}"
            blank += 1
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
            renamed += 1
        seen.setdefault(name, 1)
        names.append(name)
    if blank:
        notes.append(f"{blank} column(s) had no header and were named 'Column N'.")
    if renamed:
        notes.append(f"{renamed} duplicate column name(s) were made unique.")
    return names, notes


def _check_shape(rows: int, cols: int) -> None:
    if cols > config.MAX_COLS:
        raise CleanSheetError(f"The file has more than {config.MAX_COLS} columns.", 400, "too_many_columns")
    if rows > config.MAX_ROWS:
        raise CleanSheetError(f"The file has more than {config.MAX_ROWS:,} rows.", 400, "too_many_rows")
    if rows * cols > config.MAX_CELLS:
        raise CleanSheetError("The file has too many cells to process safely.", 400, "too_many_cells")


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def _detect_encoding(path: Path) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        decoder = codecs.getincrementaldecoder(enc)()
        try:
            with open(path, "rb") as fh:
                while chunk := fh.read(_CHUNK * 4):
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _detect_delimiter(path: Path, encoding: str) -> str:
    with open(path, "r", encoding=encoding, errors="replace", newline="") as fh:
        first = ""
        for line in fh:
            if line.strip():
                first = line
                break
    best, best_n = ",", 1
    for delim in (",", ";", "\t", "|"):
        try:
            n = len(next(csv.reader([first], delimiter=delim)))
        except (csv.Error, StopIteration):
            n = 1
        if n > best_n:
            best, best_n = delim, n
    return best


def load_csv(path: Path) -> tuple[pd.DataFrame, list[str]]:
    encoding = _detect_encoding(path)
    delim = _detect_delimiter(path, encoding)
    notes: list[str] = []
    if delim != ",":
        notes.append("Detected the separator " + {";": "semicolon (;)", "\t": "tab", "|": "pipe (|)"}[delim] + ".")
    if encoding != "utf-8-sig":
        notes.append("The file is not UTF-8; it was read as Windows-1252/Latin-1 text.")
    chunks: list[pd.DataFrame] = []
    rows = 0
    try:
        reader = pd.read_csv(path, header=None, dtype=str, keep_default_na=False, na_filter=False,
                             sep=delim, encoding=encoding, chunksize=100_000,
                             on_bad_lines="error", skip_blank_lines=True)
        for chunk in reader:
            if not chunks:
                _check_shape(0, chunk.shape[1])
            rows += len(chunk)
            _check_shape(max(rows - 1, 0), chunk.shape[1])
            chunks.append(chunk.astype(object))
    except pd.errors.EmptyDataError:
        raise CleanSheetError("The file has no data.", 400, "empty_file") from None
    except pd.errors.ParserError:
        raise CleanSheetError(
            "The CSV could not be read: some rows have more fields than the header row.", 400, "bad_csv") from None
    if not chunks:
        raise CleanSheetError("The file has no data.", 400, "empty_file")
    raw = pd.concat(chunks, ignore_index=True)
    names, header_notes = clean_headers(raw.iloc[0].tolist())
    df = raw.iloc[1:].reset_index(drop=True)
    df.columns = names
    df = df.mask(df.eq(""))             # empty cells become missing (NaN)
    return df, notes + header_notes


# --------------------------------------------------------------------------- #
# XLSX
# --------------------------------------------------------------------------- #
def cell_to_text(v) -> str | None:
    """Spreadsheet cell value -> text. Numbers lose a pointless '.0'; dates become ISO text."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else format(v, ".15g")
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time(0) else v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, (dt.date, dt.time)):
        return v.isoformat()
    text = str(v)
    return text if text != "" else None


def _trim_row(raw: tuple) -> tuple:
    """Drop trailing empty cells. Excel pads every row to the sheet's declared width, which is far wider than
    the real data when whole columns were formatted (`A1:XFD50`), so a 3-column sheet could look 16,384 wide."""
    end = len(raw)
    while end and raw[end - 1] is None:
        end -= 1
    return raw[:end]


_FORMULA_TAG = re.compile(rb"<f[ >/]")


def _workbook_has_formulas(path: Path) -> bool:
    """True when any worksheet stores a formula. A streaming byte scan: nothing is parsed and nothing is kept."""
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if not (info.filename.startswith("xl/worksheets/") and info.filename.endswith(".xml")):
                continue
            tail = b""
            with zf.open(info) as fh:
                while chunk := fh.read(_CHUNK):
                    if _FORMULA_TAG.search(tail + chunk):
                        return True
                    tail = chunk[-3:]
    return False


def _is_formula(v) -> bool:
    return (isinstance(v, str) and v.startswith("=")) or type(v).__name__ in ("ArrayFormula", "DataTableFormula")


def _unsaved_formula_warnings(path: Path, sheet: str) -> list[str]:
    """Warn about formula cells that carry no saved result.

    Excel stores each formula's last result beside it, and that result is what CleanSheet reads. A workbook
    written by a script or library often has formulas but no results, so those cells would load as empty and
    look like missing data. Best effort: a failure here never stops the upload.
    """
    from openpyxl import load_workbook

    try:
        if not _workbook_has_formulas(path):
            return []
        wb_formulas = load_workbook(path, read_only=True, data_only=False)
        wb_results = load_workbook(path, read_only=True, data_only=True)
        counts: dict[str, int] = {}
        try:
            ws_f, ws_v = wb_formulas[sheet], wb_results[sheet]
            cap = None if ws_v.max_column is None else min(ws_v.max_column, config.MAX_COLS + 1)
            header: list[str] | None = None
            pairs = zip_longest(ws_f.iter_rows(max_col=cap, values_only=True),
                                ws_v.iter_rows(max_col=cap, values_only=True), fillvalue=())
            for row_f, row_v in pairs:
                if header is None:
                    if all(c is None or str(c).strip() == "" for c in row_v):
                        continue
                    header = [cell_to_text(c) or f"Column {i + 1}" for i, c in enumerate(row_v)]
                    continue
                for i, (f, v) in enumerate(zip_longest(row_f, row_v)):
                    if v is None and _is_formula(f):
                        name = header[i] if i < len(header) else f"Column {i + 1}"
                        counts[name] = counts.get(name, 0) + 1
        finally:
            wb_formulas.close()
            wb_results.close()
    except Exception:                                   # diagnostic only; the file itself already loaded
        log.warning("could not check the workbook for unsaved formula results")
        return []
    if not counts:
        return []
    shown = ", ".join(f"'{n}'" for n in list(counts)[:5]) + ("…" if len(counts) > 5 else "")
    return [f"{sum(counts.values()):,} formula cell(s) in {len(counts)} column(s) ({shown}) have no saved result, so "
            "they were loaded as empty cells. If you expect values there, open the file in Excel or LibreOffice, "
            "save it, and upload it again."]


def load_xlsx(path: Path) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Returns (frame, notes, warnings)."""
    from openpyxl import load_workbook

    notes: list[str] = []
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception:
        raise CleanSheetError("This file is not a valid .xlsx workbook.", 400, "invalid_spreadsheet") from None
    try:
        header: list | None = None
        rows: list[list[str | None]] = []
        used = None
        for ws in wb.worksheets:
            header, rows = None, []
            # Never read (or pad rows to) more than one column past the limit: that is enough to notice a
            # genuinely too-wide sheet, and it keeps an inflated declared width from costing time and memory.
            cap = None if ws.max_column is None else min(ws.max_column, config.MAX_COLS + 1)
            for raw in ws.iter_rows(max_col=cap, values_only=True):
                raw = _trim_row(raw)
                if header is None:
                    if all(c is None or str(c).strip() == "" for c in raw):
                        continue
                    header = [cell_to_text(c) for c in raw]
                    _check_shape(0, len(header))
                    continue
                if all(c is None or (isinstance(c, str) and c.strip() == "") for c in raw):
                    continue
                if len(rows) >= config.MAX_ROWS:
                    raise CleanSheetError(
                        f"The file has more than {config.MAX_ROWS:,} rows.", 400, "too_many_rows")
                rows.append([cell_to_text(c) for c in raw])
            if header is not None:
                used = ws.title
                break
        if header is None:
            raise CleanSheetError("The workbook has no data.", 400, "empty_file")
        if len(wb.worksheets) > 1:
            notes.append(f"Only the first sheet with data ('{used}') was loaded; "
                         f"{len(wb.worksheets) - 1} other sheet(s) were ignored.")
    except CleanSheetError:
        raise
    except Exception:
        raise CleanSheetError("The workbook could not be read.", 400, "invalid_spreadsheet") from None
    finally:
        wb.close()

    width = max([len(header)] + [len(r) for r in rows]) if rows else len(header)
    header = header + [None] * (width - len(header))
    # Drop trailing columns that have no header and no data at all (common leftover formatting).
    keep = [i for i in range(width)
            if header[i] not in (None, "") or any(i < len(r) and r[i] is not None for r in rows)]
    header = [header[i] for i in keep]
    _check_shape(len(rows), len(header))
    names, header_notes = clean_headers(header)
    data = [[(r[i] if i < len(r) else None) for i in keep] for r in rows]
    df = pd.DataFrame(data, columns=names, dtype=object)
    return df, notes + header_notes, _unsaved_formula_warnings(path, used)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def load_path(path: Path, display: str) -> LoadedFile:
    """Validate the bytes of an already-saved upload and parse it. `display` is the sanitised file name."""
    fmt = validate_content(path, extension_of(display))
    warnings: list[str] = []
    if fmt == "csv":
        df, notes = load_csv(path)
    else:
        df, notes, warnings = load_xlsx(path)
    if df.shape[1] == 0:
        raise CleanSheetError("The file has no columns.", 400, "empty_file")
    if len(df) == 0:
        if warnings:                      # every cell is a formula with no saved result: say so, not "no data rows"
            raise CleanSheetError(warnings[0], 400, "unsaved_formulas")
        raise CleanSheetError("The file has a header row but no data rows.", 400, "empty_file")
    return LoadedFile(df=df, filename=display, fmt=fmt, notes=notes, warnings=warnings)


def load_upload(stream, filename: str | None) -> LoadedFile:
    """Save an upload to a unique temp file, validate it, parse it, and always delete the temp file."""
    display = safe_display_name(filename)
    ext = extension_of(display)
    if ext not in config.ALLOWED_EXTENSIONS:
        raise CleanSheetError("Only .csv and .xlsx files are supported.", 400, "bad_extension")
    with temp_upload_path(ext) as path:
        save_stream(stream, path)
        return load_path(path, display)

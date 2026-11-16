"""JSON API for the three-step workspace.

    POST /api/upload            raw file body (X-Filename header)  -> loads the file, starts a session
    GET  /api/state             what the session holds (lets the page restore itself after a reload)
    POST /api/basic/apply       Step 1: always rebuilt from the original upload
    POST /api/advanced/analysis Step 2: column types, and the controls that are relevant for each column
    POST /api/advanced/apply    Step 2: always rebuilt from the basic-cleaned dataset
    GET  /api/download/{stage}/{fmt}   stage = basic | final, fmt = csv | xlsx
    POST /api/reset             forget the loaded file
"""
from __future__ import annotations

import logging
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .. import config
from ..core import basic, convert, export, files, missing, pipeline, text
from ..core.errors import CleanSheetError
from ..core.preview import preview_pair, simple_preview
from ..core.profiling import public_profile
from ..core.validation import validate_date_formats, validate_overrides
from ..sessions import Session, store
from .helpers import SafeJSON, current_session, read_json

log = logging.getLogger("cleansheet.api")
router = APIRouter(prefix="/api")


def limits() -> dict:
    return {"max_upload_mb": config.MAX_UPLOAD_MB, "max_rows": config.MAX_ROWS, "max_cols": config.MAX_COLS,
            "extensions": sorted(config.ALLOWED_EXTENSIONS), "missing_tokens": list(config.MISSING_TOKENS)}


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


# --------------------------------------------------------------------------- #
# Session description
# --------------------------------------------------------------------------- #
def describe(s: Session) -> dict:
    out = {"has_data": True, "filename": s.filename, "format": s.fmt, "rows": int(len(s.original)),
           "columns": int(s.original.shape[1]), "notes": s.notes, "load_warnings": s.load_warnings,
           "scan": s.scan, "preview": s.upload_preview, "basic": None, "final": None, "limits": limits()}
    if s.basic is not None:
        out["basic"] = {"report": s.basic_report, "options": s.basic_options, "preview": s.basic_preview}
    if s.final is not None:
        out["final"] = {"report": s.final_report, "preview": s.final_preview, "plan": s.final_plan}
    return out


@router.get("/state")
def state(request: Request):
    s = store.find(request.cookies.get(config.SESSION_COOKIE))
    return _no_store(SafeJSON(describe(s) if s else {"has_data": False, "limits": limits()}))


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
@router.post("/upload")
async def upload(request: Request):
    raw_name = unquote(request.headers.get("x-filename") or "")
    display = files.safe_display_name(raw_name)
    ext = files.extension_of(display)
    if ext not in config.ALLOWED_EXTENSIONS:
        raise CleanSheetError("Only .csv and .xlsx files are supported.", 400, "bad_extension")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > config.MAX_UPLOAD_BYTES:
        raise CleanSheetError(f"The file is larger than the {config.MAX_UPLOAD_MB} MB limit.", 413, "too_large")

    with files.temp_upload_path(ext) as path:                       # unique name, always removed afterwards
        size = 0
        with open(path, "wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    raise CleanSheetError(
                        f"The file is larger than the {config.MAX_UPLOAD_MB} MB limit.", 413, "too_large")
                out.write(chunk)
        loaded = await run_in_threadpool(files.load_path, path, display)

    scan = await run_in_threadpool(basic.scan, loaded.df)
    store.delete(request.cookies.get(config.SESSION_COOKIE))        # one file per browser: replace the old one
    s = store.create(filename=loaded.filename, fmt=loaded.fmt, notes=loaded.notes, original=loaded.df,
                     scan=scan, upload_preview=simple_preview(loaded.df), load_warnings=loaded.warnings)
    log.info("file loaded: %s, %d rows x %d columns", loaded.fmt, len(loaded.df), loaded.df.shape[1])
    response = SafeJSON(describe(s))
    response.set_cookie(config.SESSION_COOKIE, s.sid, max_age=config.SESSION_TTL_SECONDS, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https", path="/")
    return _no_store(response)


# --------------------------------------------------------------------------- #
# Step 1 - basic cleaning
# --------------------------------------------------------------------------- #
@router.post("/basic/apply")
async def basic_apply(body: dict = Depends(read_json), s: Session = Depends(current_session)):
    return await run_in_threadpool(_basic_apply, s, body)


def _basic_apply(s: Session, body: dict):
    opts = basic.clean_options(body)
    with s.lock:
        df, report = basic.apply_basic(s.original, opts)            # always from the untouched original
        preview = preview_pair(s.original, df)
        discarded = s.set_basic(df, opts, report, preview)
    return _no_store(SafeJSON({"report": report, "preview": preview, "options": opts,
                               "advanced_discarded": discarded}))


# --------------------------------------------------------------------------- #
# Step 2 - advanced cleaning
# --------------------------------------------------------------------------- #
def _type_choices(body: dict, df) -> tuple[dict, dict]:
    for key in ("types", "date_orders"):
        v = body.get(key)
        if v is not None and not (isinstance(v, dict) and all(isinstance(a, str) and isinstance(b, str)
                                                              for a, b in v.items())):
            raise CleanSheetError("The column-type selections were not understood.", 422, "invalid_selection")
    return validate_overrides(body.get("types"), df), validate_date_formats(body.get("date_orders"), df)


@router.post("/advanced/analysis")
async def advanced_analysis(body: dict = Depends(read_json), s: Session = Depends(current_session)):
    return await run_in_threadpool(_analysis, s, body)


def _analysis(s: Session, body: dict):
    with s.lock:
        if s.basic is None:
            raise CleanSheetError("Finish Step 1 (Basic cleaning) first.", 409, "no_basic")
        overrides, date_formats = _type_choices(body, s.basic)
        profiles = s.profiles(overrides, date_formats)
        df = s.basic
        result = {
            "rows": int(len(df)),
            "columns": [public_profile(p) for p in profiles],
            "uncertain": [p["name"] for p in profiles if p["needs_confirmation"] and not p["confirmed"]],
            "missing": missing.analyse(df, profiles),
            "text": text.describe_columns(df, profiles),
            "convert": convert.describe_columns(profiles),
        }
    return _no_store(SafeJSON(result))


@router.post("/advanced/apply")
async def advanced_apply(body: dict = Depends(read_json), s: Session = Depends(current_session)):
    return await run_in_threadpool(_advanced_apply, s, body)


def _advanced_apply(s: Session, body: dict):
    with s.lock:
        if s.basic is None:
            raise CleanSheetError("Finish Step 1 (Basic cleaning) first.", 409, "no_basic")
        plan, profiles = pipeline.parse_plan(body, s.basic, s.profiles)
        final, report, conv_specs = pipeline.run_advanced(s.basic, plan, profiles, s.basic_report)
        specs = export.build_specs(final, list(profiles.values()), conv_specs)
        preview = preview_pair(s.basic, final)
        s.set_final(final, report, preview, specs, body)
    return _no_store(SafeJSON({"report": report, "preview": preview}))


# --------------------------------------------------------------------------- #
# Downloads
# --------------------------------------------------------------------------- #
@router.get("/download/{stage}/{fmt}")
def download(stage: str, fmt: str, s: Session = Depends(current_session)):
    if stage not in ("basic", "final") or fmt not in ("csv", "xlsx"):
        raise CleanSheetError("Unknown download.", 404, "not_found")
    with s.lock:
        if stage == "basic":
            df = s.basic
            if df is None:
                raise CleanSheetError("Apply Step 1 (Basic cleaning) before downloading.", 409, "no_basic")
            specs = export.build_specs(df, s.profiles({}, {})) if fmt == "xlsx" else None
        else:
            df, specs = s.final, s.final_specs
            if df is None:
                raise CleanSheetError("Apply Step 2 (Advanced cleaning) before downloading the final file.",
                                      409, "no_final")
        data = export.csv_bytes(df) if fmt == "csv" else export.xlsx_bytes(df, specs)
        name = export.download_name(s.filename, stage, fmt)
    response = Response(content=data, media_type=export.CSV_MIME if fmt == "csv" else export.XLSX_MIME)
    response.headers["Content-Disposition"] = export.content_disposition(name)
    return _no_store(response)


# --------------------------------------------------------------------------- #
# Reset
# --------------------------------------------------------------------------- #
@router.post("/reset")
def reset(request: Request):
    store.delete(request.cookies.get(config.SESSION_COOKIE))
    response = SafeJSON({"ok": True})
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return _no_store(response)

"""CleanSheet - FastAPI application.

Run:  uvicorn app.main:app --host 127.0.0.1 --port 8000      (or: python run.py)

Privacy: files are processed in this process only. Nothing is sent to another service, uploaded cell
contents are never logged, and error messages shown to people never include internals or tracebacks.
"""
from __future__ import annotations

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .api.helpers import SafeJSON
from .api.routes import limits, router
from .core import files
from .core.errors import CleanSheetError
from .learn_content import GROUPS, TOPICS, validate_topics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cleansheet")

templates = Jinja2Templates(directory=str(config.TEMPLATE_DIR))

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
]


class SecurityHeaders:
    """Pure-ASGI middleware (it never touches request bodies, so streaming uploads are unaffected)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    h for h in SECURITY_HEADERS if h[0] not in existing]
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _crash_site(exc: BaseException) -> str:
    """Where an unexpected error happened, without the message (messages can quote cell values)."""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    last = frames[-1]
    return f"{last.filename.rsplit('/', 1)[-1]}:{last.lineno} in {last.name}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_topics()
    removed = files.purge_stale_temp_files()
    if removed:
        log.info("removed %d stale temporary file(s)", removed)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="CleanSheet", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(SecurityHeaders)
    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
    app.include_router(router)

    @app.exception_handler(CleanSheetError)
    async def handle_expected(_: Request, exc: CleanSheetError):
        return SafeJSON({"error": exc.message, "code": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, __: RequestValidationError):
        return SafeJSON({"error": "The request was not understood.", "code": "bad_request"}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            messages = {404: "Not found.", 405: "That action is not allowed here."}
            return SafeJSON({"error": messages.get(exc.status_code, "The request could not be completed."),
                             "code": "http_error"}, status_code=exc.status_code)
        return SafeJSON({"error": "Page not found." if exc.status_code == 404 else "Request failed."},
                        status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception):
        log.error("unexpected %s at %s", type(exc).__name__, _crash_site(exc))   # never the message or the data
        return SafeJSON({"error": "Something went wrong while processing your file. Nothing was changed. "
                                  "Check the file and try again.", "code": "internal_error"}, status_code=500)

    @app.get("/", include_in_schema=False)
    def workspace(request: Request):
        return templates.TemplateResponse(request, "workspace.html",
                                          {"nav_current": "workspace", "limits": limits()})

    @app.get("/learn", include_in_schema=False)
    def learn(request: Request):
        return templates.TemplateResponse(request, "learn.html",
                                          {"nav_current": "learn", "topics": TOPICS, "groups": GROUPS})

    return app


app = create_app()

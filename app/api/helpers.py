"""Small HTTP helpers shared by the routes: safe JSON output, bounded JSON input, session lookup."""
from __future__ import annotations

import json
import math

import numpy as np
from fastapi import Request
from fastapi.responses import JSONResponse

from .. import config
from ..core.errors import CleanSheetError
from ..sessions import Session, store


def clean_json(obj):
    """Make a structure JSON-safe: numpy scalars become Python numbers, NaN/inf become null."""
    if isinstance(obj, dict):
        return {str(k): clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


class SafeJSON(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(clean_json(content), ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")


async def read_json(request: Request) -> dict:
    """The request body as a JSON object, refusing anything that is not JSON or is larger than the limit."""
    if not (request.headers.get("content-type") or "").lower().startswith("application/json"):
        raise CleanSheetError("The request must be JSON.", 415, "bad_content_type")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > config.MAX_JSON_BYTES:
        raise CleanSheetError("The request is too large.", 413, "too_large")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > config.MAX_JSON_BYTES:
            raise CleanSheetError("The request is too large.", 413, "too_large")
    try:
        data = json.loads(bytes(body) or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise CleanSheetError("The request was not valid JSON.", 400, "bad_json") from None
    if not isinstance(data, dict):
        raise CleanSheetError("The request must be a JSON object.", 400, "bad_json")
    return data


def current_session(request: Request) -> Session:
    return store.get(request.cookies.get(config.SESSION_COOKIE))

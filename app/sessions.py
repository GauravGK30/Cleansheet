"""In-memory sessions: one per browser, holding the three datasets of the workflow.

    original  the upload, never modified
    basic     result of Step 1 (always built from `original`); this is the input of Step 2
    final     result of Step 2 (always built from `basic`)

Because every step is rebuilt from the dataset before it, repeating a step or moving back and forth can never
apply a change twice. Re-applying Step 1 discards `final`, since it was built from the old `basic`.
Nothing is written to disk; sessions expire after SESSION_TTL_SECONDS of inactivity.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import pandas as pd

from . import config
from .core.errors import CleanSheetError
from .core.profiling import profile_frame

_PROFILE_CACHE_SIZE = 4


@dataclass
class Session:
    sid: str
    filename: str
    fmt: str
    notes: list[str]
    original: pd.DataFrame
    scan: dict
    upload_preview: dict
    load_warnings: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # Step 1 result
    basic: pd.DataFrame | None = None
    basic_options: dict | None = None
    basic_report: dict | None = None
    basic_preview: dict | None = None

    # Step 2 result
    final: pd.DataFrame | None = None
    final_report: dict | None = None
    final_preview: dict | None = None
    final_specs: dict | None = None
    final_plan: dict | None = None

    _profiles: OrderedDict = field(default_factory=OrderedDict, repr=False)

    # ---- Step 1 ---------------------------------------------------------- #
    def set_basic(self, df: pd.DataFrame, options: dict, report: dict, preview: dict) -> bool:
        """Store a new basic-cleaned dataset. Returns True when an earlier Step 2 result was discarded."""
        had_final = self.final is not None
        self.basic, self.basic_options, self.basic_report, self.basic_preview = df, options, report, preview
        self.clear_final()
        self._profiles.clear()
        return had_final

    def clear_final(self) -> None:
        self.final = self.final_report = self.final_preview = None
        self.final_specs = self.final_plan = None

    # ---- Step 2 ---------------------------------------------------------- #
    def profiles(self, overrides: dict | None = None, date_formats: dict | None = None) -> list[dict]:
        """Column profiles of the basic-cleaned dataset (cached: profiling is the slowest read-only step)."""
        if self.basic is None:
            raise CleanSheetError("Finish Step 1 (Basic cleaning) first.", 409, "no_basic")
        overrides, date_formats = overrides or {}, date_formats or {}
        key = json.dumps([overrides, date_formats], sort_keys=True)
        if key in self._profiles:
            self._profiles.move_to_end(key)
            return self._profiles[key]
        result = profile_frame(self.basic, overrides, True, date_formats)
        self._profiles[key] = result
        while len(self._profiles) > _PROFILE_CACHE_SIZE:
            self._profiles.popitem(last=False)
        return result

    def set_final(self, df, report, preview, specs, plan) -> None:
        """Store a Step 2 result. `plan` is what the browser sent, kept so the page can restore its form."""
        self.final, self.final_report, self.final_preview = df, report, preview
        self.final_specs, self.final_plan = specs, plan


class SessionStore:
    def __init__(self, ttl: int | None = None, max_sessions: int | None = None) -> None:
        self.ttl = config.SESSION_TTL_SECONDS if ttl is None else ttl
        self.max_sessions = config.MAX_SESSIONS if max_sessions is None else max_sessions
        self._items: dict[str, Session] = {}
        self._guard = threading.Lock()

    def _purge_locked(self) -> None:
        cutoff = time.time() - self.ttl
        for sid in [k for k, v in self._items.items() if v.touched < cutoff]:
            del self._items[sid]

    def create(self, **fields) -> Session:
        with self._guard:
            self._purge_locked()
            while len(self._items) >= self.max_sessions:          # make room: drop the least recently used
                oldest = min(self._items.values(), key=lambda s: s.touched)
                del self._items[oldest.sid]
            sid = secrets.token_urlsafe(32)
            session = Session(sid=sid, **fields)
            self._items[sid] = session
            return session

    def get(self, sid: str | None) -> Session:
        with self._guard:
            self._purge_locked()
            session = self._items.get(sid or "")
            if session is None:
                raise CleanSheetError(
                    "Your file is no longer loaded (it may have expired or been replaced). Upload it again.",
                    404, "no_session")
            session.touched = time.time()
            return session

    def find(self, sid: str | None) -> Session | None:
        try:
            return self.get(sid)
        except CleanSheetError:
            return None

    def delete(self, sid: str | None) -> None:
        with self._guard:
            self._items.pop(sid or "", None)

    def clear(self) -> None:
        with self._guard:
            self._items.clear()

    def __len__(self) -> int:
        with self._guard:
            return len(self._items)


store = SessionStore()

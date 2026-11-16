"""Shared fixtures. Every test gets a fresh in-memory session store and its own temporary directory, so
tests never see each other's uploads and nothing is left behind on disk."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import config                       # noqa: E402
from app.main import create_app              # noqa: E402
from app.sessions import store               # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path / "cleansheet_tmp")
    # When the configured folder is unsafe the app makes a fresh one with tempfile.mkdtemp(). Point that at the
    # test's own folder so such tests cannot leave empty cleansheet_* folders behind in the real /tmp.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    store.clear()
    yield
    store.clear()


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def quiet_client():
    """A client that returns a 500 response instead of re-raising (to test how errors are reported)."""
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c

"""Real-browser tests. They start the actual app on a local port and drive it with Chromium (Playwright).

They are skipped automatically when Playwright or its Chromium build is not installed:

    pip install -r requirements-dev.txt
    python -m playwright install chromium
    pytest tests/e2e
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed (see requirements-dev.txt)")
import uvicorn                                            # noqa: E402
from playwright.sync_api import sync_playwright           # noqa: E402

from app import config                                    # noqa: E402
from app.main import create_app                           # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CSV = ROOT / "sample_data" / "retail_orders_messy.csv"
SAMPLE_XLSX = ROOT / "sample_data" / "retail_orders_messy.xlsx"


def pytest_collection_modifyitems(items):
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def live_url(tmp_path_factory):
    """The real app, served on a free local port for the whole run."""
    config.TEMP_DIR = tmp_path_factory.mktemp("e2e_uploads") / "cleansheet_tmp"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "the test server did not start"
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:                          # Chromium not installed
            pytest.skip(f"Chromium is not available ({type(exc).__name__}); run: python -m playwright install chromium")
        yield b
        b.close()


class Problems(list):
    """Everything the page itself complained about: console errors, uncaught exceptions, failed requests."""


@pytest.fixture()
def page(browser, live_url):
    context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    p = context.new_page()
    p.problems = Problems()
    p.on("console", lambda m: p.problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    p.on("pageerror", lambda e: p.problems.append(f"pageerror: {e}"))
    p.on("response", lambda r: p.problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    p.base = live_url
    yield p
    context.close()


# ----------------------------------------------------------------------------- helpers used by the tests
def upload(page, path_or_file) -> None:
    page.goto(page.base + "/")
    page.set_input_files("#file-input", path_or_file)
    page.wait_for_selector("#loaded:not([hidden])")


def apply_basic(page) -> dict:
    page.click("#apply-basic")
    # On a re-apply the old results are still on screen, so waiting for them would read stale numbers. The button
    # says "Cleaning…" and is disabled for exactly as long as the request is running.
    # (A function, not an expression string: the app's Content-Security-Policy forbids eval.)
    page.wait_for_function("() => { const b = document.getElementById('apply-basic');"
                           " return !b.disabled && b.textContent === 'Apply basic cleaning'; }")
    page.wait_for_selector("#basic-results .tiles")
    return tiles(page, "#basic-results")


def tiles(page, scope: str) -> dict:
    """{'Original rows': '126', ...} from the summary tiles inside `scope` (raw text, not CSS-uppercased)."""
    return page.evaluate("""(scope) => Object.fromEntries([...document.querySelectorAll(scope + ' .tile')]
        .map(t => [t.querySelector('dt').textContent.trim(), t.querySelector('dd').textContent.trim()]))""", scope)


def stray_words(page) -> list:
    """Text nodes that are literally 'null' or 'undefined' outside data tables: the signature of passing a null
    to a native DOM append(). (Cells of the data tables may legitimately hold such words.)"""
    return page.evaluate("""() => {
      const bad = [], w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (w.nextNode()) {
        const n = w.currentNode, t = n.nodeValue.trim();
        if ((t === 'null' || t === 'undefined') && !n.parentElement.closest('table')) {
          bad.push(n.parentElement.tagName.toLowerCase() + '.' + n.parentElement.className);
        }
      }
      return bad;
    }""")


def go_step2(page) -> None:
    page.click("text=Continue to Step 2")
    page.wait_for_selector("#s2-body:not([hidden])")


def card(page, tab: str, column: str):
    c = page.locator(f'#tabpanel-{tab} details.col-card[data-name="{column.lower()}"]')
    if c.get_attribute("open") is None:
        c.locator("summary").click()
    return c


def apply_step2(page) -> dict:
    page.click("#s2-apply")
    page.wait_for_selector("#s3-body .tiles")
    return tiles(page, "#s3-body")


def horizontal_overflow(page) -> bool:
    w = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    return w[0] > w[1] + 1

"""The Learn Data Cleaning section, its separation from the workspace, and the project's "no AI" rule."""
from __future__ import annotations

import re
import xml.dom.minidom
from pathlib import Path

import pytest
from helpers import api_ok, csv_bytes, upload

from app import config
from app.learn_content import EXPECTED_TITLES, GROUPS, TOPICS, validate_topics

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = config.STATIC_DIR / "img" / "learn"


# --------------------------------------------------------------------------- #
# Learn page content
# --------------------------------------------------------------------------- #
def test_all_fifteen_required_topics_exist_in_order():
    assert [t["title"] for t in TOPICS] == EXPECTED_TITLES
    assert len(TOPICS) == 15
    validate_topics()


@pytest.mark.parametrize("topic", TOPICS, ids=[t["slug"] for t in TOPICS])
def test_every_topic_teaches_what_the_brief_asks_for(topic):
    assert topic["title"] and topic["summary"] and topic["why"]                      # name, explanation, why useful
    assert topic["when_use"] and topic["when_avoid"]                                  # when / when NOT
    ex = topic["example"]
    assert ex["before"] and ex["after"] and ex["columns"]                             # small before-and-after example
    assert topic["image_alt"].strip() and (IMG_DIR / topic["image"]).is_file()        # illustration, described for readers


def test_the_learn_page_renders_every_topic_with_its_illustration(client):
    page = client.get("/learn")
    assert page.status_code == 200
    html = page.text
    assert html.count('class="topic"') == 15
    for t in TOPICS:
        assert f'id="{t["slug"]}"' in html and f"/static/img/learn/{t['image']}" in html
    for heading in ("Why it helps", "Use it when", "Do not use it when", "Before and after"):
        assert html.count(heading) == 15
    assert [g for g in GROUPS if g in html] == GROUPS


@pytest.mark.parametrize("svg", sorted(IMG_DIR.glob("*.svg")), ids=lambda p: p.name)
def test_illustrations_are_valid_self_contained_svg(svg):
    text = svg.read_text(encoding="utf-8")
    root = xml.dom.minidom.parseString(text).documentElement             # well-formed XML or this raises
    assert root.tagName == "svg" and root.getAttribute("viewBox")
    assert "<script" not in text.lower() and "onload" not in text.lower()
    assert not re.search(r"(href|src)\s*=\s*[\"']https?://", text) and "url(http" not in text   # nothing remote


def test_every_illustration_file_is_used_by_a_topic_and_every_topic_has_a_distinct_one():
    used = [t["image"] for t in TOPICS]
    assert len(set(used)) == len(used)
    assert {p.name for p in IMG_DIR.glob("*.svg")} == set(used)


def test_illustrations_are_served_as_images_by_the_app(client):
    r = client.get(f"/static/img/learn/{TOPICS[0]['image']}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")


# --------------------------------------------------------------------------- #
# Separation: teaching never touches the workspace, and the workspace carries no teaching
# --------------------------------------------------------------------------- #
def test_the_workspace_contains_no_educational_images_or_topic_articles(client):
    html = client.get("/").text
    assert "/static/img/learn/" not in html and 'class="topic"' not in html
    for js in (config.STATIC_DIR / "js").glob("*.js"):
        assert "img/learn" not in js.read_text(encoding="utf-8"), js.name


def test_the_learn_page_has_no_upload_controls_and_no_workspace_scripts(client):
    html = client.get("/learn").text
    assert 'type="file"' not in html and "/static/js/" not in html and "<form" not in html


def test_reading_the_learn_page_never_changes_an_uploaded_dataset(client):
    api_ok(upload(client, csv_bytes(["a", "b"], [["1", "2"], ["3", "4"]]), "d.csv"))
    before = client.get("/api/state").json()
    for t in TOPICS:
        assert client.get(f"/learn#{t['slug']}").status_code == 200
    r = client.get("/learn")
    assert "set-cookie" not in r.headers                                   # the page does not even use a session
    assert client.get("/api/state").json() == before


def test_the_learn_page_works_without_any_upload(client):
    assert client.get("/learn").status_code == 200 and client.get("/api/state").json()["has_data"] is False


def test_workspace_links_into_the_learn_page_for_each_stage(client):
    html = client.get("/").text
    assert 'href="/learn#remove-duplicates"' in html and 'href="/learn#handling-missing-values"' in html
    assert 'href="/learn"' in html                                         # the main navigation entry


# --------------------------------------------------------------------------- #
# Privacy: nothing leaves the server
# --------------------------------------------------------------------------- #
def test_pages_load_nothing_from_other_websites(client):
    for url in ("/", "/learn"):
        html = client.get(url).text
        assert not re.search(r"""(?:src|href|action)\s*=\s*["']\s*(?:https?:)?//""", html), url
    for path in (config.STATIC_DIR / "js").glob("*.js"):
        assert not re.search(r"""fetch\(\s*["']https?://|import\s+.*["']https?://""", path.read_text(encoding="utf-8")), path.name
    for path in (config.STATIC_DIR / "css").glob("*.css"):
        assert "@import" not in path.read_text(encoding="utf-8") and "url(http" not in path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The "no AI" rule, enforced
# --------------------------------------------------------------------------- #
BANNED_PACKAGES = {"openai", "anthropic", "cohere", "google.generativeai", "langchain", "llama_index", "transformers",
                   "torch", "tensorflow", "keras", "sklearn", "scikit-learn", "xgboost", "lightgbm", "spacy", "nltk",
                   "huggingface_hub", "sentence_transformers", "fuzzywhuzzy", "thefuzz", "rapidfuzz", "dateparser"}


def _imports(source: str) -> set[str]:
    names = set()
    for line in source.splitlines():
        m = re.match(r"\s*(?:from|import)\s+([A-Za-z_][\w.]*)", line)
        if m:
            names.add(m.group(1))
    return names


def test_no_ai_or_machine_learning_library_is_imported_anywhere_in_the_app():
    offenders = []
    for path in list((ROOT / "app").rglob("*.py")) + [ROOT / "run.py"]:
        for name in _imports(path.read_text(encoding="utf-8")):
            if name in BANNED_PACKAGES or name.split(".")[0] in BANNED_PACKAGES:
                offenders.append((path.name, name))
    assert offenders == []


def test_requirements_list_no_ai_package_and_no_api_key_is_needed():
    for name in ("requirements.txt", "requirements-dev.txt"):
        text = (ROOT / name).read_text(encoding="utf-8").lower()
        for banned in BANNED_PACKAGES:
            assert not re.search(rf"^\s*{re.escape(banned)}\b", text, re.M), (name, banned)
    source = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "app").rglob("*.py"))
    assert not re.search(r"api[_-]?key|ANTHROPIC|OPENAI|Authorization", source, re.I)


def test_the_app_makes_no_outgoing_network_calls():
    source = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "app").rglob("*.py"))
    for needle in ("requests.", "urllib.request", "http.client", "aiohttp", "httpx", "socket.", "smtplib", "urlopen"):
        assert needle not in source, needle

"""The three-step workflow driven through a real browser (Chromium) against the real server.

These cover what unit and API tests cannot see: that the page really renders, that the buttons do what the
labels say, that navigating between steps never repeats a change, and that no screen shows stray text such as
the word "null".
"""
from __future__ import annotations

import io

import pandas as pd
import pytest
from openpyxl import load_workbook

from .conftest import (SAMPLE_CSV, SAMPLE_XLSX, apply_basic, apply_step2, card, go_step2, horizontal_overflow,
                       stray_words, tiles, upload)


def confirm_uncertain_columns(page) -> None:
    """The sample's 'newsletter' column holds only 1s and 0s, so the app asks instead of guessing."""
    while page.locator(".confirm-row button:has-text('Confirm')").count():
        page.locator(".confirm-row button:has-text('Confirm')").first.click()
        page.wait_for_selector("#s2-body:not([hidden])")


def download(page, button_text: str, tmp_path, name: str):
    with page.expect_download() as info:
        page.click(f"button:has-text('{button_text}')")
    target = tmp_path / name
    info.value.save_as(str(target))
    return info.value.suggested_filename, target


# ----------------------------------------------------------------------------- the whole journey
def test_full_workflow_with_a_csv_file_and_both_download_formats(page, tmp_path):
    upload(page, str(SAMPLE_CSV))
    assert "126 rows" in page.inner_text("#file-meta")

    # ---- Step 1
    page.select_option("#binary-list select >> nth=0", "true_false")     # is_returned: Yes/No -> TRUE/FALSE
    t = apply_basic(page)
    assert (t["Original rows"], t["Cleaned rows"], t["Duplicate rows removed"]) == ("126", "120", "6")
    assert t["Yes/No columns"] == "1 of 3"                                  # only the one the user chose
    assert stray_words(page) == []

    # Option A: the basic-cleaned data can be downloaded without going further
    name, path = download(page, "Download CSV", tmp_path, "basic.csv")
    assert name == "retail_orders_messy_basic_cleaned.csv"
    basic_csv = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert len(basic_csv) == 120 and set(basic_csv["is_returned"]) <= {"TRUE", "FALSE", ""}
    name, path = download(page, "Download XLSX", tmp_path, "basic.xlsx")
    assert name.endswith("_basic_cleaned.xlsx") and len(list(load_workbook(path).active.rows)) == 121

    # ---- Step 2 (Option B): every choice is optional; make four
    go_step2(page)
    confirm_uncertain_columns(page)
    assert page.locator("#tabpanel-missing details.col-card").count() == 12         # only columns that have gaps
    card(page, "missing", "quantity").locator("select").first.select_option("median")
    card(page, "missing", "revenue").locator("select").first.select_option("formula")
    card(page, "missing", "customer").locator("select").first.select_option("mapping")
    notes = card(page, "missing", "notes")
    notes.locator("select").first.select_option("custom")
    notes.locator(".extra input").fill("Not provided")
    assert "Will fill 26 cells" in notes.locator(".outcome").inner_text()           # the effect is shown first
    # identifiers are never offered an average, dates never get one either
    ident = card(page, "missing", "customer_id").locator("select").first.locator("option").all_inner_texts()
    assert not any("mean" in o.lower() or "median" in o.lower() for o in ident)

    page.click("#tab-text")
    cust = card(page, "text", "customer")
    cust.locator("select").first.select_option("title")
    page.click("#tab-types")
    page.locator('#tabpanel-types tr[data-name="quantity"] select').select_option("integer")
    page.locator('#tabpanel-types tr[data-name="ship_date"] select').select_option("date")   # has invalid dates
    ids = page.locator('#tabpanel-types tr[data-name="customer_id"] select option').all_inner_texts()
    assert ids == ["Keep original", "Text (keep as text)"]                  # identifiers only ever stay text

    # ---- Step 3
    t = apply_step2(page)
    assert (t["Original rows"], t["Basic-cleaned rows"], t["Final rows"]) == ("126", "120", "120")
    assert t["Missing values"].startswith("57 →")
    assert t["Conversions completed"] == "1" and "skipped" in t["Conversions completed"] + \
        page.locator("#s3-body .tile:has-text('Conversions completed') .tile-cap").inner_text()
    warning = page.locator("#s3-body .alert-warn").inner_text()
    assert "ship_date" in warning and "'soon'" in warning and "YYYY-MM-DD" in warning and "%" not in warning
    assert stray_words(page) == []

    _, csv_path = download(page, "Download final CSV", tmp_path, "final.csv")
    final = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    assert len(final) == 120
    assert (final["quantity"] == "").sum() == 0 and (final["revenue"] == "").sum() == 0
    assert (final["customer"] == "").sum() == 0 and (final["notes"] == "").sum() == 0
    filled_ids = final.loc[final["customer_id"] != "", "customer_id"]       # 2 gaps were deliberately kept
    assert len(filled_ids) == 118 and filled_ids.str.startswith("00").all() # leading zeros survived
    assert final["ship_date"].str.contains("soon").any()                    # the skipped column is untouched

    _, xlsx_path = download(page, "Download final XLSX", tmp_path, "final.xlsx")
    sheet = load_workbook(xlsx_path).active
    header = [c.value for c in sheet[1]]
    first = {h: c for h, c in zip(header, sheet[2])}
    assert first["customer_id"].data_type == "s" and str(first["customer_id"].value).startswith("00")
    assert isinstance(first["quantity"].value, int)                         # converted: a real number, not text
    assert page.problems == []


def test_a_xlsx_upload_goes_through_the_workflow_too(page):
    upload(page, str(SAMPLE_XLSX))
    assert page.inner_text("#file-meta").endswith("XLSX")
    t = apply_basic(page)
    assert (t["Original rows"], t["Cleaned rows"]) == ("126", "120")
    go_step2(page)
    t = apply_step2(page)                                                   # an empty plan is allowed
    assert t["Final rows"] == "120" and t["Conversions completed"] == "0"
    assert "identical to the basic-cleaned dataset" in page.inner_text("#s3-body")
    assert page.problems == []


# ----------------------------------------------------------------------------- navigation never repeats work
def test_going_back_and_forth_never_applies_anything_twice(page):
    upload(page, str(SAMPLE_CSV))
    first_basic = apply_basic(page)
    go_step2(page)
    confirm_uncertain_columns(page)
    card(page, "missing", "quantity").locator("select").first.select_option("median")
    first_final = apply_step2(page)

    # Step 3 -> Step 2: the choices are still there; applying again gives the very same numbers
    page.click("text=← Back to Advanced cleaning")
    page.wait_for_selector("#s2-body:not([hidden])")
    assert "fill 4 cells" in page.inner_text("#plan-summary")
    again = apply_step2(page)
    assert again == first_final

    # Step 3 -> Step 1: pressing Apply again starts from the ORIGINAL upload, so nothing is cleaned twice
    page.click("text=Back to Basic cleaning")
    second_basic = apply_basic(page)
    assert second_basic == first_basic                                      # still 6 duplicates, not 0
    assert second_basic["Duplicate rows removed"] == "6"
    assert "Step 2 results were cleared" in page.inner_text("#basic-results")
    assert page.locator('.step-tab[data-step="3"]').is_disabled()           # the stale final file is gone
    assert page.locator('.step-tab[data-step="2"]').is_enabled()            # the basic data is kept for Step 2

    go_step2(page)                                                          # selections kept where they still apply
    assert "fill 4 cells" in page.inner_text("#plan-summary")
    assert apply_step2(page) == first_final


def test_changing_choices_after_applying_marks_the_review_out_of_date_and_pauses_downloads(page):
    upload(page, str(SAMPLE_CSV))
    apply_basic(page)
    go_step2(page)
    confirm_uncertain_columns(page)
    apply_step2(page)
    assert page.locator("button:has-text('Download final CSV')").is_enabled()

    page.click("text=← Back to Advanced cleaning")
    page.wait_for_selector("#s2-body:not([hidden])")
    card(page, "missing", "quantity").locator("select").first.select_option("median")
    page.click('.step-tab[data-step="3"]')
    assert "This review is out of date" in page.inner_text("#s3-body")
    assert page.locator("button:has-text('Download final CSV')").is_disabled()
    assert page.locator("button:has-text('Download final XLSX')").is_disabled()


def test_reloading_the_page_restores_the_stage_the_person_was_on(page):
    upload(page, str(SAMPLE_CSV))
    apply_basic(page)
    go_step2(page)
    confirm_uncertain_columns(page)
    apply_step2(page)
    page.reload()
    page.wait_for_selector("#s3-body .tiles")
    assert page.locator("#panel-3").is_visible()
    page.click("text=Back to Basic cleaning")
    assert page.locator("#basic-results .tiles").is_visible()               # Step 1 result is still there


# ----------------------------------------------------------------------------- rendering details
def test_a_small_file_shows_no_stray_null_text_anywhere(page, tmp_path):
    """Regression: with six or fewer columns the Data types tab, and every Step 3, printed the word 'null'."""
    small = tmp_path / "small.csv"
    small.write_text("id,name,age,joined\n001,ann lee,34,2024-01-05\n002,BO CHEN,N/A,2024-02-11\n"
                     "003,cy diaz,40,2024-03-09\n004,di ono,37,2024-04-22\n")
    upload(page, str(small))
    apply_basic(page)
    assert stray_words(page) == []
    go_step2(page)
    for tab in ("missing", "text", "types"):
        page.click(f"#tab-{tab}")
        assert stray_words(page) == [], f"stray text on the {tab} tab"
    apply_step2(page)
    assert stray_words(page) == []
    assert page.problems == []


def test_a_cell_containing_html_is_shown_as_text_and_never_runs(page, tmp_path):
    evil = tmp_path / "evil.csv"
    evil.write_text('name,note\n"<img src=x onerror=window.__pwned=1>",hello\n"<script>window.__pwned=2</script>",hi\n')
    upload(page, str(evil))
    apply_basic(page)
    assert page.evaluate("window.__pwned") is None
    assert "<img src=x onerror=window.__pwned=1>" in page.inner_text("#basic-results")
    assert page.locator("#basic-results img").count() == 0
    # the strict Content-Security-Policy blocks inline script, so the browser reports it; that is the point
    assert all("Content Security Policy" in p or "HTTP" not in p for p in page.problems)


def test_a_bad_file_shows_a_friendly_message_and_no_internals(page):
    page.goto(page.base + "/")
    page.set_input_files("#file-input", {"name": "report.xlsx", "mimeType": "application/octet-stream",
                                         "buffer": b"this is plainly not a workbook"})
    page.wait_for_selector("#messages .alert-error")
    message = page.inner_text("#messages")
    assert "not a valid .xlsx" in message
    for leak in ("Traceback", "File \"", "Error:", ".py", "pandas", "openpyxl"):
        assert leak not in message
    assert page.locator("#upload-card").is_visible()                        # the person can simply try again


def test_column_names_that_collide_with_javascript_internals_work_like_any_other(page, tmp_path):
    """Regression: per-column choices were kept in plain objects, so a header such as 'constructor', 'toString'
    or '__proto__' stopped Step 2 from opening (showing a raw JavaScript error), or made a choice vanish."""
    import csv

    path = tmp_path / "odd_headers.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["order_ref", "constructor", "__proto__", "toString", "valueOf", "hasOwnProperty"])
        for i in range(1, 13):
            w.writerow([f"R{i:02d}",
                        "" if i in (2, 7) else ["north", "south", "east"][i % 3],
                        "" if i in (3, 8) else ["alpha", "beta", "gamma"][i % 3],
                        "" if i in (4, 9) else str(i * 10),
                        ["red", "RED", "Blue", "  green "][i % 4],
                        ["Yes", "No"][i % 2]])
    upload(page, str(path))
    page.select_option("#binary-list select >> nth=0", "true_false")      # 'hasOwnProperty' is the Yes/No column
    apply_basic(page)
    go_step2(page)                                          # used to fail: "undefined is not iterable"
    confirm_uncertain_columns(page)
    assert page.inner_text("#messages").strip() == ""

    # nothing has been chosen yet, so every card must say so (an inherited 'constructor' used to look like a choice)
    for name in ("constructor", "__proto__", "toString"):
        c = card(page, "missing", name)
        assert c.locator("select").first.input_value() == "keep", name
        assert "No change" in c.locator(".outcome").inner_text(), name

    proto = card(page, "missing", "__proto__")
    proto.locator("select").first.select_option("custom")
    proto.locator(".extra input").fill("zzz")
    card(page, "missing", "toString").locator("select").first.select_option("median")
    assert "fill 4 cells" in page.inner_text("#plan-summary")
    page.click("#tab-text")
    card(page, "text", "valueOf").locator("select").first.select_option("title")
    t = apply_step2(page)
    assert t["Final rows"] == "12" and stray_words(page) == []

    final = pd.read_csv(download(page, "Download final CSV", tmp_path, "odd_final.csv")[1],
                        dtype=str, keep_default_na=False)
    assert final.loc[final["__proto__"] == "zzz", "order_ref"].tolist() == ["R03", "R08"]   # the choice was sent
    assert final.loc[[3, 8], "toString"].tolist() == ["65", "65"]                           # median of the other ten
    assert (final["constructor"] == "").sum() == 2                                          # left alone, as chosen
    assert set(final["valueOf"]) == {"Red", "Blue", "Green"}
    assert set(final["hasOwnProperty"]) == {"TRUE", "FALSE"}                                # Step 1 choice was sent

    page.reload()                                           # the saved plan is read back from the server
    page.wait_for_selector("#s3-body .tiles")
    page.click("text=← Back to Advanced cleaning")
    page.wait_for_selector("#s2-body:not([hidden])")
    assert "fill 4 cells" in page.inner_text("#plan-summary")
    assert card(page, "missing", "__proto__").locator("select").first.input_value() == "custom"
    page.click("text=← Back to Step 1")
    assert page.locator("#binary-list select").first.input_value() == "true_false"        # restored, not blank
    assert page.problems == []


def test_a_fault_in_the_page_shows_a_plain_sentence_not_a_javascript_error(page):
    """A server message is written for people and is shown as it is. A fault in the page itself (here: an answer of
    the wrong shape, as a bug would cause) must never put raw JavaScript text such as 'undefined is not iterable'
    in front of the person."""
    upload(page, str(SAMPLE_CSV))
    apply_basic(page)
    page.route("**/api/advanced/analysis", lambda route: route.fulfill(
        status=200, content_type="application/json", body='{"rows": 1}'))
    page.click("text=Continue to Step 2")
    page.wait_for_selector("#messages .alert-error")
    message = page.inner_text("#messages")
    assert "Something went wrong in the page" in message
    for leak in ("undefined", "iterable", "Cannot read", "TypeError", "null", "map"):
        assert leak not in message
    assert page.locator("#s2-body").is_hidden()


# ----------------------------------------------------------------------------- phones
@pytest.mark.parametrize("width", [390, 768])
def test_no_screen_scrolls_sideways_on_a_phone_or_tablet(browser, live_url, width):
    context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.base = live_url
    try:
        page.goto(live_url + "/")
        assert not horizontal_overflow(page), "empty workspace"
        page.set_input_files("#file-input", str(SAMPLE_CSV))
        page.wait_for_selector("#loaded:not([hidden])")
        assert not horizontal_overflow(page), "Step 1 with a file"
        apply_basic(page)
        assert not horizontal_overflow(page), "Step 1 results"
        go_step2(page)
        confirm_uncertain_columns(page)
        for tab in ("missing", "text", "types"):
            page.click(f"#tab-{tab}")
            assert not horizontal_overflow(page), f"Step 2 {tab} tab"
        apply_step2(page)
        assert not horizontal_overflow(page), "Step 3"
        page.goto(live_url + "/learn")
        assert not horizontal_overflow(page), "Learn page"
    finally:
        context.close()


# ----------------------------------------------------------------------------- Learn page
def test_the_learn_page_is_separate_teaches_all_fifteen_methods_and_all_images_load(page):
    page.goto(page.base + "/learn")
    assert page.locator("section.topic").count() == 15
    assert page.locator("input[type=file]").count() == 0                    # no way to upload or modify data here
    images = page.locator(".topic img")
    assert images.count() == 15
    for i in range(images.count()):                                         # images are lazy: scroll each into view
        images.nth(i).scroll_into_view_if_needed()
        page.wait_for_function("(i) => { const el = document.querySelectorAll('.topic img')[i];"
                               " return el.complete && el.naturalWidth > 0; }", arg=i, timeout=5000)
    for section in page.locator("section.topic").all()[:3]:                 # each topic has every required part
        text = section.inner_text().lower()
        for part in ("why it helps", "use it when", "do not use it when", "before and after"):
            assert part in text
    assert page.problems == []


def test_the_workspace_has_no_educational_content_and_only_links_to_learn(page):
    upload(page, str(SAMPLE_CSV))
    apply_basic(page)
    go_step2(page)
    assert page.locator("img[src*='/img/learn/']").count() == 0
    assert page.locator("section.topic").count() == 0
    links = page.locator("a[href^='/learn']").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert links and all(h.startswith("/learn") for h in links)

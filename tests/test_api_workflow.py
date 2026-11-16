"""The three-step workflow through the real HTTP API: Basic -> Advanced -> Review & export.

These are the tests for navigation between stages and for "never apply a change twice". They use the same
endpoints and cookies the browser uses.
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import pytest
from helpers import api_ok, basic_options, csv_bytes, upload, xlsx_bytes

from app import config

HEADER = ["order_id", "customer_id", "customer", "city", "quantity", "unit_price", "revenue", "order_date",
          "is_returned", "notes"]
SECRET = "ZZ-PRIVATE-CELL-VALUE"


def orders_rows() -> list[list]:
    """12 orders + 1 duplicate that only differs by padding. Known gaps (after Step 1):
    revenue row 4 blank, quantity row 7 'N/A', customer row 5 blank, city row 9 '-', notes 'none' x3."""
    customers = {"00101": "Asha Rao", "00102": "Ben Carter", "00103": "Chloe Martin"}
    prices = [2.5, 4, 3, 5, 2, 6, 3.5, 4.5, 2.5, 5.5, 3, 4]
    rows = []
    for i in range(12):
        cid = list(customers)[i % 3]
        qty = i + 1
        rows.append([f"ORD-{1000 + i}", cid, customers[cid], ["Pune", "Delhi"][i % 2], str(qty),
                     f"{prices[i]:.2f}", f"{qty * prices[i]:.2f}", f"2024-{1 + i % 9:02d}-{10 + i % 9:02d}",
                     ["Yes", "No"][i % 2], "none" if i % 4 == 0 else f"note {i}"])
    rows[3][6] = None                       # revenue blank (4 x 5.00 = 20.00 is recoverable)
    rows[6][4] = "N/A"                      # quantity placeholder
    rows[4][2] = None                       # customer blank (customer_id 00102 is Ben Carter elsewhere)
    rows[8][3] = "-"                        # city placeholder
    dup = list(rows[0])
    dup[2] = "  Asha Rao "                  # same row once trimmed
    return rows + [dup]


@pytest.fixture()
def loaded(client):
    api_ok(upload(client, csv_bytes(HEADER, orders_rows()), "orders.csv"))
    return client


def basic(client, **changes):
    return api_ok(client.post("/api/basic/apply", json=basic_options(**changes)))


def advanced(client, plan=None):
    return api_ok(client.post("/api/advanced/apply", json=plan or {}))["report"]


def analysis(client, body=None):
    return api_ok(client.post("/api/advanced/analysis", json=body or {}))


def table(response) -> pd.DataFrame:
    text = response.content.decode("utf-8-sig")
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False).replace({"": None})


PLAN = {
    "missing": {"quantity": {"action": "median"},
                "revenue": {"action": "formula", "formula": {"op": "multiply", "a": "quantity", "b": "unit_price"}},
                "customer": {"action": "mapping", "key": "customer_id"},
                "notes": {"action": "custom", "value": "Not provided"}},
    "text": {"city": {"case": "upper", "trim": True, "collapse": True, "replace": []}},
    "convert": {"quantity": {"to": "integer"}, "order_date": {"to": "date"}},
}


# --------------------------------------------------------------------------- #
# Step 1
# --------------------------------------------------------------------------- #
def test_upload_describes_the_file_and_sets_a_private_cookie(client):
    r = upload(client, csv_bytes(HEADER, orders_rows()), "orders.csv")
    body = api_ok(r)
    assert (body["rows"], body["columns"], body["format"]) == (13, 10, "csv")
    assert body["scan"]["duplicate_rows"] == 1
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_basic_cleaning_reports_every_number_the_workflow_promises(loaded):
    report = basic(loaded)["report"]
    assert report["original_rows"] == 13 and report["cleaned_rows"] == 12
    assert report["duplicates_removed"] == 1
    assert report["missing_tokens_normalised"] == 6              # N/A, -, and 'none' x4 (before the duplicate left)
    assert report["missing_after"] == 7                          # revenue, quantity, customer, city, notes x3
    assert report["whitespace_cells_changed"] == 1
    assert report["binary_detected"] == 1                        # is_returned


def test_step_1_can_be_applied_to_a_subset_of_columns_for_duplicates(loaded):
    report = basic(loaded, dedupe_mode="subset", dedupe_columns=["city"])["report"]
    assert report["cleaned_rows"] == 3                           # Pune, Delhi and the '-' placeholder (now missing)


def test_reapplying_step_1_never_stacks_on_a_previous_result(loaded):
    first = basic(loaded)
    second = basic(loaded)
    assert first["report"] == second["report"]
    assert second["report"]["duplicates_removed"] == 1           # not 0, which it would be if it re-cleaned the output
    again = basic(loaded, remove_duplicates=False)
    assert again["report"]["cleaned_rows"] == 13                 # starts from the untouched upload each time


def test_the_basic_download_is_the_basic_cleaned_data_in_both_formats(loaded):
    basic(loaded, binary={"is_returned": "true_false"})
    csv = table(loaded.get("/api/download/basic/csv"))
    assert len(csv) == 12 and csv["is_returned"].dropna().isin(["TRUE", "FALSE"]).all()
    assert csv["customer_id"].str.startswith("00").all()          # leading zeros survive
    xlsx = loaded.get("/api/download/basic/xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert xlsx.headers["content-disposition"].startswith("attachment")


# --------------------------------------------------------------------------- #
# Stage gating
# --------------------------------------------------------------------------- #
def test_later_stages_are_refused_until_the_earlier_one_is_done(loaded):
    for method, url in [("post", "/api/advanced/analysis"), ("post", "/api/advanced/apply"),
                        ("get", "/api/download/basic/csv"), ("get", "/api/download/final/csv")]:
        r = getattr(loaded, method)(url, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 409, url
    basic(loaded)
    assert loaded.get("/api/download/basic/csv").status_code == 200
    assert loaded.get("/api/download/final/csv").status_code == 409     # Step 2 has not been applied yet


def test_without_an_upload_every_stage_says_the_file_is_gone(client):
    for method, url in [("post", "/api/basic/apply"), ("post", "/api/advanced/apply"),
                        ("get", "/api/download/basic/csv")]:
        r = getattr(client, method)(url, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 404 and r.json()["code"] == "no_session"
    assert client.get("/api/state").json()["has_data"] is False


# --------------------------------------------------------------------------- #
# Step 2 and Step 3
# --------------------------------------------------------------------------- #
def test_advanced_cleaning_starts_from_the_basic_cleaned_data_not_the_original(loaded):
    basic(loaded)
    a = analysis(loaded)
    assert a["rows"] == 12                                       # the duplicate is already gone
    by_name = {c["name"]: c for c in a["columns"]}
    assert by_name["customer_id"]["kind"] == "identifier" and by_name["revenue"]["kind"] == "calculated"
    # only columns that really have gaps are offered a missing-value control
    assert {m["name"] for m in a["missing"]} == {"customer", "city", "quantity", "revenue", "notes"}


def test_a_full_plan_is_applied_and_reported(loaded):
    basic(loaded)
    report = advanced(loaded, PLAN)
    assert (report["rows_original"], report["rows_basic"], report["rows_final"]) == (13, 12, 12)
    assert report["missing_basic"] == 7 and report["missing_final"] == 1      # only city remains
    assert report["cells_filled"] == 6 and report["conversions_completed"] == 2
    assert report["rows_removed"] == 0 and report["operations_skipped"] == 0
    final = table(loaded.get("/api/download/final/csv"))
    assert final.loc[3, "revenue"] == "20.00"                    # 4 x 5.00, calculated and not averaged
    assert final.loc[6, "quantity"] == "6"                       # median of the other eleven quantities
    assert final.loc[4, "customer"] == "Ben Carter"              # recovered from customer_id
    assert final["notes"].isna().sum() == 0 and (final["notes"] == "Not provided").sum() == 3
    assert final["city"].dropna().isin(["PUNE", "DELHI"]).all() and final["city"].isna().sum() == 1
    assert final["customer_id"].str.startswith("00").all()


def test_an_invalid_conversion_is_skipped_with_a_warning_and_the_rest_still_apply(loaded):
    basic(loaded)
    plan = {"convert": {"unit_price": {"to": "integer"}, "order_date": {"to": "date"}}}
    report = advanced(loaded, plan)
    assert report["conversions_completed"] == 1 and report["conversions_skipped"] == 1
    assert any("unit_price" in w and "original values were kept" in w for w in report["warnings"])
    final = table(loaded.get("/api/download/final/csv"))
    assert final["unit_price"].tolist() == [f"{p:.2f}" for p in [2.5, 4, 3, 5, 2, 6, 3.5, 4.5, 2.5, 5.5, 3, 4]]


def test_applying_step_2_twice_gives_the_same_file_and_never_changes_twice(loaded):
    basic(loaded)
    plan = {"missing": {"quantity": {"action": "remove"}, "notes": {"action": "custom", "value": "x"}},
            "text": {"city": {"case": "title", "trim": False, "collapse": False,
                              "replace": [{"find": "Pune", "replace": "Pune City"}]}}}
    first = advanced(loaded, plan)
    file_1 = loaded.get("/api/download/final/csv").content
    second = advanced(loaded, plan)
    file_2 = loaded.get("/api/download/final/csv").content
    assert file_1 == file_2
    assert first["rows_final"] == second["rows_final"] == 11     # removing rows happens once, not twice
    assert b"Pune City City" not in file_2                       # a replace never compounds
    assert first["rows_basic"] == second["rows_basic"] == 12


def test_an_empty_plan_is_allowed_and_leaves_the_data_unchanged(loaded):
    basic(loaded)
    report = advanced(loaded, {})
    assert report["empty_plan"] is True and report["columns_modified"] == 0
    assert loaded.get("/api/download/final/csv").content == loaded.get("/api/download/basic/csv").content


def test_step_2_never_overwrites_the_intermediate_basic_dataset(loaded):
    basic(loaded)
    before = loaded.get("/api/download/basic/csv").content
    advanced(loaded, PLAN)
    assert loaded.get("/api/download/basic/csv").content == before
    assert loaded.get("/api/download/final/csv").content != before


# --------------------------------------------------------------------------- #
# Navigation between stages
# --------------------------------------------------------------------------- #
def test_going_back_and_reapplying_step_1_discards_the_stale_final_result(loaded):
    basic(loaded)
    advanced(loaded, PLAN)
    assert loaded.get("/api/download/final/csv").status_code == 200
    r = basic(loaded, trim=False)
    assert r["advanced_discarded"] is True
    assert loaded.get("/api/download/final/csv").status_code == 409      # built from the old basic data: gone
    assert loaded.get("/api/state").json()["final"] is None
    report = advanced(loaded, {})                                         # and Step 2 can simply be run again
    assert report["rows_basic"] == 13        # trimming is off now, so the padded copy is no longer a duplicate


def test_reapplying_step_1_with_identical_options_gives_identical_data(loaded):
    basic(loaded)
    one = loaded.get("/api/download/basic/csv").content
    advanced(loaded, PLAN)
    basic(loaded)
    two = loaded.get("/api/download/basic/csv").content
    assert one == two


def test_the_page_can_restore_every_stage_after_a_reload(loaded):
    s0 = loaded.get("/api/state").json()
    assert s0["has_data"] and s0["basic"] is None and s0["final"] is None
    basic(loaded)
    s1 = loaded.get("/api/state").json()
    assert s1["basic"]["report"]["cleaned_rows"] == 12 and s1["final"] is None
    advanced(loaded, PLAN)
    s2 = loaded.get("/api/state").json()
    assert s2["final"]["report"]["rows_final"] == 12 and s2["final"]["plan"]["convert"] == PLAN["convert"]
    assert s2["basic"]["options"]["remove_duplicates"] is True


def test_uploading_a_new_file_replaces_everything_and_reset_forgets_it(loaded):
    basic(loaded)
    advanced(loaded, {})
    api_ok(upload(loaded, csv_bytes(["a", "b"], [["1", "2"], ["3", "4"]]), "second.csv"))
    state = loaded.get("/api/state").json()
    assert state["filename"] == "second.csv" and state["basic"] is None and state["final"] is None
    assert loaded.get("/api/download/final/csv").status_code == 409
    assert loaded.post("/api/reset").status_code == 200
    assert loaded.get("/api/state").json()["has_data"] is False


def test_xlsx_files_go_through_the_whole_workflow(client):
    api_ok(upload(client, xlsx_bytes(HEADER, orders_rows()), "orders.xlsx"))
    assert basic(client)["report"]["cleaned_rows"] == 12
    assert advanced(client, PLAN)["rows_final"] == 12
    assert client.get("/api/download/final/xlsx").content[:2] == b"PK"
    assert client.get("/api/state").json()["format"] == "xlsx"


# --------------------------------------------------------------------------- #
# Limits and validation through the API
# --------------------------------------------------------------------------- #
def test_the_default_upload_limit_is_50_mb_and_the_page_says_so(client):
    assert client.get("/api/state").json()["limits"]["max_upload_mb"] == 50
    assert "Up to 50 MB" in client.get("/").text


def test_an_upload_over_the_limit_is_refused_by_its_declared_size(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1000)
    r = upload(client, b"a,b\n" + b"1,2\n" * 500, "big.csv")
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    assert list(config.TEMP_DIR.glob("upload_*")) == []


@pytest.mark.parametrize("limit, rows, cols, code", [("MAX_ROWS", 6, 2, "too_many_rows"),
                                                     ("MAX_COLS", 2, 4, "too_many_columns")])
def test_row_and_column_limits_apply_to_uploads(client, monkeypatch, limit, rows, cols, code):
    monkeypatch.setattr(config, limit, 5 if limit == "MAX_ROWS" else 3)
    r = upload(client, csv_bytes([f"c{i}" for i in range(cols)], [[str(i)] * cols for i in range(rows)]), "x.csv")
    assert r.status_code == 400 and r.json()["code"] == code


@pytest.mark.parametrize("name, data, code", [("notes.txt", b"a\n1\n", "bad_extension"),
                                              ("empty.csv", b"", "empty_file"),
                                              ("fake.xlsx", b"not a workbook", "invalid_spreadsheet"),
                                              ("sheet.csv", xlsx_bytes(["a"], [[1]]), "content_mismatch")])
def test_the_extension_alone_is_never_trusted(client, name, data, code):
    r = upload(client, data, name)
    assert r.status_code == 400 and r.json()["code"] == code


def test_unsafe_selections_are_rejected_not_executed(loaded):
    basic(loaded)
    bad = [{"missing": {"nope": {"action": "mean"}}}, {"missing": {"city": {"action": "mean"}}},
           {"text": {"customer_id": {"case": "lower"}}}, {"convert": {"customer_id": {"to": "integer"}}},
           {"missing": "x"}, {"types": {"city": "bogus"}}]
    for plan in bad:
        r = loaded.post("/api/advanced/apply", json=plan)
        assert r.status_code == 422, plan
        assert "Traceback" not in r.text
    assert loaded.get("/api/download/final/csv").status_code == 409    # nothing was applied by the rejected plans


def test_non_json_and_oversized_json_bodies_are_refused(loaded, monkeypatch):
    basic(loaded)
    assert loaded.post("/api/advanced/apply", content=b"{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert loaded.post("/api/advanced/apply", content=b"{nope", headers={"Content-Type": "application/json"}).status_code == 400
    monkeypatch.setattr(config, "MAX_JSON_BYTES", 50)
    big = loaded.post("/api/advanced/apply", json={"text": {"x" * 200: {}}})
    assert big.status_code == 413


# --------------------------------------------------------------------------- #
# Privacy and safe failure
# --------------------------------------------------------------------------- #
def test_responses_carry_security_headers(client):
    for url in ("/", "/learn", "/api/state"):
        h = client.get(url).headers
        assert "default-src 'self'" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert client.get("/api/state").headers["cache-control"] == "no-store"


def test_cell_contents_are_never_written_to_the_log(client, caplog):
    rows = [[SECRET, "00123", "x"], [SECRET, "00123", "x"], ["b", None, "N/A"]]
    with caplog.at_level(logging.DEBUG):
        api_ok(upload(client, csv_bytes(["name", "id", "note"], rows), f"{SECRET}.csv"))
        basic(client)
        advanced(client, {"missing": {"id": {"action": "custom", "value": SECRET}}})
        client.get("/api/download/final/csv")
        client.get("/api/download/final/xlsx")
        client.post("/api/advanced/apply", json={"missing": {SECRET: {"action": "mean"}}})     # a rejected plan
    assert SECRET not in caplog.text
    assert "00123" not in caplog.text


def test_an_unexpected_crash_shows_a_generic_message_and_leaks_nothing(quiet_client, monkeypatch, caplog):
    from app.core import pipeline

    def boom(*_a, **_k):
        raise RuntimeError(f"internal detail with {SECRET}")

    api_ok(upload(quiet_client, csv_bytes(["a", "b"], [[SECRET, "1"], ["y", "2"]]), "f.csv"))
    basic(quiet_client)
    monkeypatch.setattr(pipeline, "run_advanced", boom)
    with caplog.at_level(logging.DEBUG):
        r = quiet_client.post("/api/advanced/apply", json={})
    assert r.status_code == 500 and r.json()["code"] == "internal_error"
    body = r.text
    assert SECRET not in body and "RuntimeError" not in body and "Traceback" not in body and ".py" not in body
    assert SECRET not in caplog.text                              # the log names where it failed, never the message

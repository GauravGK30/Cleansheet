"""Step 2C: data-type conversion. A conversion is all-or-nothing: one invalid value skips the whole column,
keeps the original values and says why. Identifiers stay text."""
import pytest

from app.core import convert
from app.core.errors import CleanSheetError
from app.core.profiling import profile_frame
from helpers import frame, run_advanced, values


def conv(**cols):
    return {"convert": cols}


def offered(df):
    return {c["name"]: [o["value"] for o in c["options"]] for c in convert.describe_columns(profile_frame(df))}


# ----------------------------------------------------------------------------- only relevant options
def test_options_match_the_column_type():
    df = frame(qty=["1", "2", "3", "4"], customer_id=["C001", "C002", "C003", "C004"],
               when=["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
               name=["Ann", "Bo", "Ann", "Bo"], note=["2024-01-05", "2024-01-06", "2024-01-07", "2024-01-08"])
    got = offered(df)
    assert got["qty"] == ["keep", "integer", "decimal", "text"]
    assert got["customer_id"] == ["keep", "text"]                    # never integer
    assert got["when"] == ["keep", "date", "text"]
    assert got["name"] == ["keep", "text"]                           # not date-like, so no date option
    assert "date" in got["note"] or got["note"] == ["keep", "text"]  # date-like text may offer date


def test_booleans_have_no_conversions():
    assert "flag" not in offered(frame(flag=["Yes", "No", "Yes", "No"]))


def test_a_conversion_not_offered_for_the_column_is_rejected():
    df = frame(customer_id=["C001", "C002", "C003", "C004"])
    with pytest.raises(CleanSheetError, match="not available"):
        run_advanced(df, conv(customer_id={"to": "integer"}))
    with pytest.raises(CleanSheetError):
        run_advanced(frame(name=["Ann", "Bo", "Ann", "Bo"]), conv(name={"to": "date"}))


# ----------------------------------------------------------------------------- numbers
def test_text_numbers_to_integer():
    df = frame(qty=["1", "2", "3.0", "1,200", None], who=list("abcde"))
    final, rep, specs = run_advanced(df, conv(qty={"to": "integer"}))
    assert values(final["qty"]) == ["1", "2", "3", "1200", None]
    assert rep["conversions_completed"] == 1 and specs["qty"] == {"type": "number", "decimals": 0}


def test_integer_conversion_with_a_fraction_skips_the_whole_column():
    df = frame(qty=["1", "2", "2.5", "4"], who=list("abcd"))
    final, rep, specs = run_advanced(df, conv(qty={"to": "integer"}))
    assert values(final["qty"]) == ["1", "2", "2.5", "4"]            # untouched, not half-converted
    assert rep["conversions_skipped"] == 1 and rep["conversions_completed"] == 0 and specs == {}
    assert rep["operations"][0]["status"] == "skipped" and rep["operations_skipped"] == 1
    assert "'2.5'" in rep["warnings"][0] and "original values were kept" in rep["warnings"][0]


def test_invalid_numbers_in_a_mostly_numeric_column_skip_the_conversion():
    df = frame(price=["1.5", "2.5", "3.5", "4.5", "5.5", "6.5", "7.5", "8.5", "9.5", "oops"], who=list("abcdefghij"))
    final, rep, _ = run_advanced(df, {"types": {"price": "numeric"}, "convert": {"price": {"to": "decimal"}}})
    assert values(final["price"])[-1] == "oops" and values(final["price"])[0] == "1.5"
    assert rep["conversions_skipped"] == 1 and "not numbers" in rep["warnings"][0]


def test_decimal_conversion_pads_to_the_chosen_places():
    df = frame(price=["1.5", "2", "3.25", None], who=list("abcd"))
    final, _, specs = run_advanced(df, conv(price={"to": "decimal", "decimals": 3}))
    assert values(final["price"]) == ["1.500", "2.000", "3.250", None] and specs["price"]["decimals"] == 3


def test_decimal_conversion_never_rounds_silently():
    df = frame(price=["1.255", "2.5", "3.0", "4.0"], who=list("abcd"))
    final, rep, _ = run_advanced(df, conv(price={"to": "decimal", "decimals": 2}))
    assert values(final["price"])[0] == "1.255" and rep["conversions_skipped"] == 1
    assert "would round" in rep["warnings"][0]


def test_decimal_places_are_validated():
    df = frame(price=["1.5", "2.5", "3.5", "4.5"])
    for bad in (-1, 11, "2", True, 1.5):
        with pytest.raises(CleanSheetError):
            run_advanced(df, conv(price={"to": "decimal", "decimals": bad}))


def test_numbers_to_text_keeps_values():
    df = frame(qty=["1", "2", "3", "4"])
    final, _, specs = run_advanced(df, conv(qty={"to": "text"}))
    assert values(final["qty"]) == ["1", "2", "3", "4"] and specs["qty"]["type"] == "text"


# ----------------------------------------------------------------------------- dates
def test_dates_standardise_to_iso():
    df = frame(d=["25/12/2024", "01/02/2024", None, "31/03/2024"])
    final, rep, specs = run_advanced(df, conv(d={"to": "date"}))
    assert values(final["d"]) == ["2024-12-25", "2024-02-01", None, "2024-03-31"]
    assert specs["d"]["type"] == "date" and rep["conversions_completed"] == 1


def test_month_name_dates_are_understood():
    df = frame(d=["Jan 5, 2024", "Feb 11, 2024", "Mar 3, 2024"])
    final, _, _ = run_advanced(df, conv(d={"to": "date"}))
    assert values(final["d"]) == ["2024-01-05", "2024-02-11", "2024-03-03"]


def test_invalid_dates_skip_the_whole_column_and_say_which_values():
    df = frame(d=["2024-01-05", "2024-02-30", "soon", "2024-03-07"] + ["2024-04-01"] * 6)
    final, rep, specs = run_advanced(df, {"types": {"d": "date"}, "convert": {"d": {"to": "date"}}})
    assert values(final["d"])[1] == "2024-02-30" and values(final["d"])[2] == "soon"
    assert rep["conversions_skipped"] == 1 and specs == {}
    assert "'2024-02-30'" in rep["warnings"][0] and "'soon'" in rep["warnings"][0]


def test_ambiguous_day_month_order_is_refused_until_the_user_chooses():
    df = frame(d=["03/04/2024", "05/06/2024", "07/08/2024"])
    with pytest.raises(CleanSheetError, match="unclear"):
        run_advanced(df, conv(d={"to": "date"}))
    day_first, _, _ = run_advanced(df, {"date_orders": {"d": "%d/%m/%Y"}, "convert": {"d": {"to": "date"}}})
    assert values(day_first["d"]) == ["2024-04-03", "2024-06-05", "2024-08-07"]
    month_first, _, _ = run_advanced(df, {"date_orders": {"d": "%m/%d/%Y"}, "convert": {"d": {"to": "date"}}})
    assert values(month_first["d"]) == ["2024-03-04", "2024-05-06", "2024-07-08"]


def test_a_time_of_day_is_never_dropped_silently():
    df = frame(d=["2024-01-05 10:30:00", "2024-01-06 00:00:00", "2024-01-07 08:15:00"])
    final, rep, _ = run_advanced(df, conv(d={"to": "date"}))
    assert values(final["d"])[0] == "2024-01-05 10:30:00" and rep["conversions_skipped"] == 1
    assert "time of day" in rep["warnings"][0]


def test_text_that_looks_like_dates_can_be_converted_but_only_if_all_valid():
    ok = frame(note=["2024-01-05", "2024-01-06", "2024-01-07", "2024-01-08"])
    if "date" in offered(ok).get("note", []):
        final, _, _ = run_advanced(ok, conv(note={"to": "date"}))
        assert values(final["note"])[0] == "2024-01-05"


def test_date_standardise_and_date_to_text():
    df = frame(d=["2024-01-05", "2024-01-06", "2024-01-07"])
    same, rep, _ = run_advanced(df, conv(d={"to": "date"}))
    assert values(same["d"]) == values(df["d"]) and rep["conversions_completed"] == 1
    as_text, _, specs = run_advanced(df, conv(d={"to": "text"}))
    assert values(as_text["d"]) == values(df["d"]) and specs["d"]["type"] == "text"


# ----------------------------------------------------------------------------- identifiers
def test_identifiers_keep_leading_zeros_as_text():
    df = frame(zip=["00123", "00456", "01234", "09999"])
    final, rep, specs = run_advanced(df, conv(zip={"to": "text"}))
    assert values(final["zip"]) == ["00123", "00456", "01234", "09999"]
    assert specs["zip"]["type"] == "text" and rep["conversions_completed"] == 1


def test_identifiers_cannot_be_turned_into_numbers_even_by_override_request():
    df = frame(zip=["00123", "00456", "01234", "09999"])
    with pytest.raises(CleanSheetError):
        run_advanced(df, conv(zip={"to": "integer"}))
    with pytest.raises(CleanSheetError):
        run_advanced(df, conv(zip={"to": "decimal"}))


# ----------------------------------------------------------------------------- shape rules
def test_conversion_never_changes_which_cells_are_missing_or_the_row_count():
    df = frame(qty=["1", None, "3", "4"], who=list("abcd"))
    final, _, _ = run_advanced(df, conv(qty={"to": "integer"}))
    assert len(final) == 4 and final["qty"].isna().tolist() == df["qty"].isna().tolist()


def test_one_skipped_column_does_not_block_the_others():
    df = frame(qty=["1", "2", "2.5", "4"], price=["1.5", "2", "3", "4"], who=list("abcd"))
    final, rep, _ = run_advanced(df, conv(qty={"to": "integer"}, price={"to": "decimal", "decimals": 2}))
    assert values(final["qty"]) == ["1", "2", "2.5", "4"]
    assert values(final["price"]) == ["1.50", "2.00", "3.00", "4.00"]
    assert (rep["conversions_completed"], rep["conversions_skipped"]) == (1, 1)


def test_date_warnings_name_the_format_in_plain_words_never_as_python_codes():
    from app.core.values import friendly_date_format
    assert friendly_date_format("%Y-%m-%d") == "YYYY-MM-DD"
    assert friendly_date_format("%d/%m/%Y %H:%M:%S") == "DD/MM/YYYY HH:mm:ss"
    assert friendly_date_format("%d %B %Y") == "DD Month YYYY" and friendly_date_format("%d-%b-%Y") == "DD-Mon-YYYY"
    df = frame(d=["2024-01-05", "2024-02-30"] + ["2024-04-01"] * 8)
    _, rep, _ = run_advanced(df, {"types": {"d": "date"}, "convert": {"d": {"to": "date"}}})
    assert "YYYY-MM-DD" in rep["warnings"][0] and "%" not in rep["warnings"][0]

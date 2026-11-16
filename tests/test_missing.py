"""Step 2A: missing-value handling. Each column kind gets only the methods that suit it, nothing is applied
silently, identifiers are never averaged or guessed, and calculated columns are only recomputed from real data."""
import pytest

from app.core import missing
from app.core.errors import CleanSheetError
from app.core.validation import MISSING_ACTIONS_BY_KIND
from helpers import frame, profiles_of, run_advanced, values


def plan(**cols):
    return {"missing": cols}


def numeric_df():
    return frame(item=["a", "b", "c", "d", "e"], price=["10.00", "20.00", None, "30.00", "20.00"])


# ----------------------------------------------------------------------------- what is offered, per kind
def test_only_columns_with_gaps_are_analysed():
    df = frame(a=["x", "y", None], b=["1", "2", "3"])
    infos = missing.analyse(df, list(profiles_of(df).values()))
    assert [i["name"] for i in infos] == ["a"]
    assert infos[0]["missing"] == 1 and infos[0]["missing_pct"] == 33.3 and infos[0]["kind"] in ("categorical", "text")


def test_allowed_actions_follow_the_brief():
    assert set(MISSING_ACTIONS_BY_KIND["numeric"]) == {"mean", "median", "mode", "custom", "remove", "keep"}
    assert set(MISSING_ACTIONS_BY_KIND["text"]) == {"mode", "custom", "mapping", "remove", "keep"}
    assert set(MISSING_ACTIONS_BY_KIND["identifier"]) == {"mapping", "custom", "remove", "keep"}
    assert set(MISSING_ACTIONS_BY_KIND["date"]) == {"mapping", "custom", "remove", "keep"}
    assert set(MISSING_ACTIONS_BY_KIND["calculated"]) == {"formula", "custom", "remove", "keep"}
    assert set(MISSING_ACTIONS_BY_KIND["boolean"]) == {"custom", "remove", "keep"}
    for kind in ("identifier", "date", "boolean", "calculated"):
        assert not {"mean", "median"} & set(MISSING_ACTIONS_BY_KIND[kind])


def test_the_analysis_only_lists_options_that_make_sense_for_the_column():
    df = frame(invoice_no=["INV-1", "INV-2", None, "INV-4", "INV-5"], price=["1.5", None, "2.5", "3.5", "4.5"])
    infos = {i["name"]: i for i in missing.analyse(df, list(profiles_of(df).values()))}
    ident = {o["value"] for o in infos["invoice_no"]["options"]}
    assert ident == {"custom", "remove", "keep"}                      # no mapping available, never mean/median
    num = {o["value"] for o in infos["price"]["options"]}
    assert {"mean", "median", "mode", "custom", "remove", "keep"} == num


# ----------------------------------------------------------------------------- numeric columns
def test_numeric_mean_median_mode_and_counts():
    for action, expected in (("mean", "20.00"), ("median", "20.00"), ("mode", "20.00")):
        final, rep, _ = run_advanced(numeric_df(), plan(price={"action": action}))
        assert values(final["price"]) == ["10.00", "20.00", expected, "30.00", "20.00"], action
        assert rep["cells_filled"] == 1 and rep["missing_basic"] == 1 and rep["missing_final"] == 0


def test_mean_differs_from_median_on_skewed_data():
    df = frame(pay=["30000", "32000", None, "34000", "250000"], who=list("abcde"))
    mean, _, _ = run_advanced(df, plan(pay={"action": "mean"}))
    median, _, _ = run_advanced(df, plan(pay={"action": "median"}))
    assert values(mean["pay"])[2] == "86500" and values(median["pay"])[2] == "33000"


def test_whole_number_columns_get_whole_number_fills():
    df = frame(qty=["1", "2", None, "4", "6"], who=list("abcde"))
    final, rep, _ = run_advanced(df, plan(qty={"action": "mean"}))
    assert values(final["qty"])[2] == "3"                            # mean 3.25 -> 3, rounded half up
    assert "Rounded to whole numbers" in rep["operations"][0]["detail"]   # the rounding is disclosed, not silent


def test_mode_tie_uses_the_smallest_value_deterministically():
    df = frame(v=["5.0", "7.0", "5.0", "7.0", None], who=list("abcde"))
    final, _, _ = run_advanced(df, plan(v={"action": "mode"}))
    assert values(final["v"])[4] == "5.0"


def test_custom_value_for_numbers_must_be_a_number():
    final, rep, _ = run_advanced(numeric_df(), plan(price={"action": "custom", "value": "99.5"}))
    assert values(final["price"])[2] == "99.5" and rep["cells_filled"] == 1
    for bad in ("abc", "", "  ", "1e999999"):
        with pytest.raises(CleanSheetError):
            run_advanced(numeric_df(), plan(price={"action": "custom", "value": bad}))


def test_remove_rows_and_keep():
    final, rep, _ = run_advanced(numeric_df(), plan(price={"action": "remove"}))
    assert len(final) == 4 and rep["rows_removed"] == 1 and rep["rows_basic"] == 5 and rep["rows_final"] == 4
    assert list(final.index) == [0, 1, 3, 4]
    kept, rep2, _ = run_advanced(numeric_df(), plan(price={"action": "keep"}))
    assert kept.equals(numeric_df()) and rep2["cells_filled"] == 0 and rep2["empty_plan"] is True


def test_removing_rows_that_would_empty_the_table_is_refused():
    df = frame(a=[None, None], b=["x", "y"])
    with pytest.raises(CleanSheetError, match="every row"):
        run_advanced(df, plan(a={"action": "remove"}))


# ----------------------------------------------------------------------------- text / categorical
def test_text_mode_and_custom():
    df = frame(city=["Pune", "Pune", None, "Delhi", "Pune"], who=list("abcde"))
    final, _, _ = run_advanced(df, plan(city={"action": "mode"}))
    assert values(final["city"])[2] == "Pune"
    final, _, _ = run_advanced(df, plan(city={"action": "custom", "value": "Unknown"}))
    assert values(final["city"])[2] == "Unknown"


def test_text_columns_cannot_use_mean():
    df = frame(city=["Pune", "Pune", None, "Delhi", "Pune"])
    with pytest.raises(CleanSheetError, match="not available"):
        run_advanced(df, plan(city={"action": "mean"}))


# ----------------------------------------------------------------------------- identifiers
def id_df():
    return frame(invoice_no=["INV-001", "INV-002", None, "INV-004", "INV-005"], who=list("abcde"))


@pytest.mark.parametrize("action", ["mean", "median", "mode", "formula"])
def test_identifiers_are_never_averaged_or_guessed(action):
    with pytest.raises(CleanSheetError, match="not available"):
        run_advanced(id_df(), plan(invoice_no={"action": action}))


def test_identifier_gaps_stay_unless_the_user_chooses_otherwise():
    final, rep, _ = run_advanced(id_df(), plan(invoice_no={"action": "keep"}))
    assert values(final["invoice_no"])[2] is None and rep["missing_final"] == 1


def test_identifier_custom_value_and_remove_are_allowed():
    final, _, _ = run_advanced(id_df(), plan(invoice_no={"action": "custom", "value": "INV-000"}))
    assert values(final["invoice_no"])[2] == "INV-000"
    final, rep, _ = run_advanced(id_df(), plan(invoice_no={"action": "remove"}))
    assert len(final) == 4 and rep["rows_removed"] == 1


def mapping_df(ambiguous=False):
    ids = ["C1", "C2", "C1", None, "C2", None, "C3"]
    names = ["Ann", "Bo", "Ann", "Ann", "Bo", "Cy", "Di"]
    if ambiguous:
        ids[2] = "C9"                        # 'Ann' now maps to two different ids
    return frame(customer_id=ids, customer=names)


def test_identifier_recovered_from_an_unambiguous_mapping_only():
    df = mapping_df()
    info = {i["name"]: i for i in missing.analyse(df, list(profiles_of(df).values()))}["customer_id"]
    assert info["mappings"] == [{"key": "customer", "recoverable": 1, "total_missing": 2}]
    final, rep, _ = run_advanced(df, plan(customer_id={"action": "mapping", "key": "customer"}))
    assert values(final["customer_id"]) == ["C1", "C2", "C1", "C1", "C2", None, "C3"]   # 'Cy' is unknown: stays empty
    assert rep["cells_filled"] == 1 and rep["missing_final"] == 1


def test_an_ambiguous_mapping_is_refused():
    df = mapping_df(ambiguous=True)
    assert missing.analyse(df, list(profiles_of(df).values()))[0]["mappings"] == []
    with pytest.raises(CleanSheetError, match="cannot reliably recover"):
        run_advanced(df, plan(customer_id={"action": "mapping", "key": "customer"}))


def test_a_mapping_key_chosen_by_the_client_is_checked_against_the_data():
    with pytest.raises(CleanSheetError):
        run_advanced(mapping_df(), plan(customer_id={"action": "mapping", "key": "no_such_column"}))
    with pytest.raises(CleanSheetError):
        run_advanced(mapping_df(), plan(customer_id={"action": "mapping", "key": "customer_id"}))


# ----------------------------------------------------------------------------- dates
def date_df():
    return frame(order_date=["2024-01-05", "2024-02-11", None, "2024-03-20", "2024-04-02"], who=list("abcde"))


def test_dates_offer_custom_remove_keep_and_never_averages():
    for action in ("mean", "median", "mode"):
        with pytest.raises(CleanSheetError, match="not available"):
            run_advanced(date_df(), plan(order_date={"action": action}))


def test_date_custom_value_is_validated():
    final, _, _ = run_advanced(date_df(), plan(order_date={"action": "custom", "value": "2024-02-29"}))
    assert values(final["order_date"])[2] == "2024-02-29"
    for bad in ("2023-02-29", "31/12/2024", "yesterday", "2024-13-01"):
        with pytest.raises(CleanSheetError):
            run_advanced(date_df(), plan(order_date={"action": "custom", "value": bad}))


def test_a_custom_date_is_written_in_the_columns_own_format():
    df = frame(d=["25/12/2024", "26/12/2024", None, "27/12/2024"])
    final, _, _ = run_advanced(df, plan(d={"action": "custom", "value": "2024-12-28"}))
    assert values(final["d"])[2] == "28/12/2024"


def test_custom_date_refused_while_day_month_order_is_unclear():
    df = frame(d=["03/04/2024", "05/06/2024", None, "07/08/2024"])
    with pytest.raises(CleanSheetError, match="unclear"):
        run_advanced(df, plan(d={"action": "custom", "value": "2024-01-02"}))


# ----------------------------------------------------------------------------- calculated columns
def calc_df():
    # revenue = quantity x unit_price on every complete row
    return frame(quantity=["1", "2", "3", "4", "5", "6", "7", None, "2"],
                 unit_price=["2.50", "4.00", "3.00", "5.50", "2.00", "9.00", "1.50", "3.00", "4.00"],
                 revenue=["2.50", "8.00", "9.00", "22.00", "10.00", "54.00", None, None, "8.00"])


def test_formula_recovery_only_where_every_source_is_present():
    df = calc_df()
    profiles = profiles_of(df)
    assert profiles["revenue"]["kind"] == "calculated"
    formula = {k: profiles["revenue"]["formulas"][0][k] for k in ("op", "a", "b")}
    final, rep, _ = run_advanced(df, plan(revenue={"action": "formula", "formula": formula}))
    out = values(final["revenue"])
    assert out[6] == "10.50"                       # 7 x 1.50, both sources present
    assert out[7] is None                          # quantity is missing: not calculated, not guessed
    assert rep["cells_filled"] == 1 and rep["missing_final"] == 2     # 1 revenue + 1 quantity still empty


def test_calculated_columns_are_never_filled_with_averages():
    for action in ("mean", "median", "mode"):
        with pytest.raises(CleanSheetError, match="not available"):
            run_advanced(calc_df(), plan(revenue={"action": action}))


def test_a_formula_that_does_not_hold_is_refused():
    bogus = {"op": "subtract", "a": "quantity", "b": "unit_price"}
    with pytest.raises(CleanSheetError, match="does not hold"):
        run_advanced(calc_df(), plan(revenue={"action": "formula", "formula": bogus}))


def test_margin_is_recovered_from_revenue_minus_cost():
    n = 8
    qty = [str(i + 1) for i in range(n)]
    price = ["5.00", "6.50", "7.00", "4.25", "9.00", "3.00", "8.00", "2.50"]
    cost_each = ["3.00", "4.00", "5.50", "2.00", "6.00", "1.50", "5.00", "1.25"]
    rev = [f"{(i + 1) * float(price[i]):.2f}" for i in range(n)]
    cost = [f"{(i + 1) * float(cost_each[i]):.2f}" for i in range(n)]
    margin = [f"{float(rev[i]) - float(cost[i]):.2f}" for i in range(n)]
    expected = margin[3]
    margin[3] = None
    df = frame(quantity=qty, unit_price=price, unit_cost=cost_each, revenue=rev, cost=cost, margin=margin)
    p = profiles_of(df)["margin"]
    assert p["kind"] == "calculated"
    f = next(f for f in p["formulas"] if (f["op"], f["a"], f["b"]) == ("subtract", "revenue", "cost"))
    final, _, _ = run_advanced(df, plan(margin={"action": "formula", "formula": {k: f[k] for k in ("op", "a", "b")}}))
    assert values(final["margin"])[3] == expected


def test_cost_prefers_quantity_times_unit_cost_over_a_derived_difference():
    n = 8
    qty = [str(i + 1) for i in range(n)]
    cost_each = ["3.00", "4.00", "5.50", "2.00", "6.00", "1.50", "5.00", "1.25"]
    price = ["5.00", "6.50", "7.00", "4.25", "9.00", "3.00", "8.00", "2.50"]
    rev = [f"{(i + 1) * float(price[i]):.2f}" for i in range(n)]
    cost = [f"{(i + 1) * float(cost_each[i]):.2f}" for i in range(n)]
    margin = [f"{float(rev[i]) - float(cost[i]):.2f}" for i in range(n)]
    cost[2] = None
    df = frame(quantity=qty, unit_price=price, unit_cost=cost_each, revenue=rev, cost=cost, margin=margin)
    first = profiles_of(df)["cost"]["formulas"][0]
    assert first["op"] == "multiply" and {first["a"], first["b"]} == {"quantity", "unit_cost"}


# ----------------------------------------------------------------------------- boolean / anomaly columns
def flag_df():
    return frame(anomaly=["TRUE", "FALSE", None, "FALSE", "TRUE"], who=list("abcde"))


def test_boolean_unknown_is_preserved_by_default():
    final, rep, _ = run_advanced(flag_df(), plan(anomaly={"action": "keep"}))
    assert values(final["anomaly"])[2] is None and rep["cells_filled"] == 0


@pytest.mark.parametrize("action", ["mean", "median", "mode"])
def test_boolean_is_never_assumed_false_or_normal(action):
    with pytest.raises(CleanSheetError, match="not available"):
        run_advanced(flag_df(), plan(anomaly={"action": action}))


def test_boolean_custom_value_must_already_exist_in_the_column():
    final, _, _ = run_advanced(flag_df(), plan(anomaly={"action": "custom", "value": "false"}))
    assert values(final["anomaly"])[2] == "FALSE"                    # matched case-insensitively, written as in the data
    with pytest.raises(CleanSheetError):
        run_advanced(flag_df(), plan(anomaly={"action": "custom", "value": "Maybe"}))


def test_boolean_remove_rows():
    final, rep, _ = run_advanced(flag_df(), plan(anomaly={"action": "remove"}))
    assert len(final) == 4 and rep["rows_removed"] == 1


# ----------------------------------------------------------------------------- safety rails
def test_unknown_columns_and_actions_are_rejected():
    with pytest.raises(CleanSheetError):
        run_advanced(numeric_df(), plan(nope={"action": "keep"}))
    with pytest.raises(CleanSheetError):
        run_advanced(numeric_df(), plan(price={"action": "explode"}))


def test_a_column_the_user_has_not_confirmed_stays_locked():
    df = frame(count=["1", "0", None, "1", "0"], who=list("abcde"))
    with pytest.raises(CleanSheetError, match="Confirm the type"):
        run_advanced(df, plan(count={"action": "custom", "value": "1"}))
    final, _, _ = run_advanced(df, {"types": {"count": "numeric"}, "missing": {"count": {"action": "median"}}})
    assert values(final["count"])[2] is not None


def test_input_frame_is_never_modified():
    df = numeric_df()
    snapshot = df.copy()
    run_advanced(df, plan(price={"action": "mean"}))
    assert df.equals(snapshot)


def test_each_operation_is_reported_with_its_effect():
    final, rep, _ = run_advanced(numeric_df(), plan(price={"action": "median"}))
    op = rep["operations"][0]
    assert op["step"] == "missing" and op["column"] == "price" and op["status"] == "applied"
    assert "Filled 1 cell" in op["detail"]


# ----------------------------------------------------------------------------- what you see is what is applied
def _shown(df, column, key):
    """The value the analysis (the numbers on screen) promises for a statistic of one column."""
    infos = {i["name"]: i for i in missing.analyse(df, list(profiles_of(df).values()))}
    return infos[column]["stats"][key]


def skewed_df():
    # Row 4 holds the outlier 1000 and is the only row with a gap in "b", so asking to remove rows with a gap
    # in "b" also removes the outlier. a's gap is row 5.
    return frame(a=["10", "10", "10", "10", "1000", None, "12", "11"],
                 b=["x", "x", "x", "x", None, "x", "x", "x"],
                 k=list("abcdefgh"))


@pytest.mark.parametrize("action", ["mean", "median", "mode"])
def test_the_fill_shown_on_screen_is_the_fill_applied_even_when_another_column_removes_rows(action):
    df = skewed_df()
    promised = _shown(df, "a", action)
    final, report, _ = run_advanced(df, plan(a={"action": action}, b={"action": "remove"}))
    assert len(final) == 7 and report["rows_removed"] == 1               # the outlier's row really was removed
    written = values(final["a"])[4]                                       # the formerly empty cell
    assert written == promised, (
        f"the screen promised {promised} for {action} but {written} was written")
    # for the mean this is the number that exposes the bug: removing the 1000 would have given 11, not 152
    if action == "mean":
        assert promised == "152"


def test_a_text_mode_shown_on_screen_is_the_mode_applied_even_when_rows_are_removed():
    # On screen "red" is the most common value (4 of 6). The three rows removed for column b are all red, so
    # computed after the removal the most common value would flip to "blue" (2 of 3).
    df = frame(c=["red", "red", "red", "red", "blue", "blue", None], b=["x", None, None, None, "x", "x", "x"])
    promised = missing.text_mode(df["c"])[0]
    assert promised == "red"
    final, _, _ = run_advanced(df, plan(c={"action": "mode"}, b={"action": "remove"}))
    assert values(final["c"]) == ["red", "blue", "blue", "red"]


def test_a_mapping_recovers_the_same_rows_it_promised_even_when_rows_are_removed():
    # Row 1 (the second "C1 -> ann" pair) is removed because "other" is empty there. Judged only on the surviving
    # rows every key would be seen once, which proves nothing, so the link would be dropped even though the screen
    # offered "fills 1 of 1". Judged on the data as shown, the gap is recoverable.
    df = frame(cust_id=["C1", "C1", "C2", "C1"], name=["ann", "ann", "ben", None], other=["x", None, "x", "x"])
    infos = {i["name"]: i for i in missing.analyse(df, list(profiles_of(df).values()))}
    assert [m["key"] for m in infos["name"]["mappings"]] == ["cust_id"]
    final, report, _ = run_advanced(df, plan(name={"action": "mapping", "key": "cust_id"},
                                             other={"action": "remove"}))
    assert report["rows_removed"] == 1
    assert values(final["name"]) == ["ann", "ben", "ann"]
    assert [o["status"] for o in report["operations"] if o["column"] == "name"] == ["applied"]

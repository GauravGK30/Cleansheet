"""Step 2B: text standardization. Optional, per column, text/category columns only; identifiers are protected."""
import pytest

from app.core.errors import CleanSheetError
from app.core.text import title_case
from helpers import frame, run_advanced, values


def text_plan(**cols):
    return {"text": cols}


def step(**kw):
    base = {"case": "preserve", "trim": False, "collapse": False, "replace": []}
    base.update(kw)
    return base


def cities():
    return frame(city=["  new  york ", "NEW YORK", "new york", "Paris", " paris"], who=list("abcde"))


# ----------------------------------------------------------------------------- the seven operations
def test_preserve_case_changes_nothing():
    final, rep, _ = run_advanced(cities(), text_plan(city=step()))
    assert final.equals(cities()) and rep["empty_plan"] is True


def test_lowercase_uppercase_titlecase():
    df = frame(city=["new YORK", "pARIS", "st. mary's road"])
    assert values(run_advanced(df, text_plan(city=step(case="lower")))[0]["city"]) == ["new york", "paris", "st. mary's road"]
    assert values(run_advanced(df, text_plan(city=step(case="upper")))[0]["city"]) == ["NEW YORK", "PARIS", "ST. MARY'S ROAD"]
    # An apostrophe stays inside its word: "mary's" -> "Mary's" (never "Mary'S"). Names like O'Neil are not guessed.
    assert values(run_advanced(df, text_plan(city=step(case="title")))[0]["city"]) == ["New York", "Paris", "St. Mary's Road"]


def test_title_case_handles_apostrophes_and_digits():
    assert title_case("don't PANIC") == "Don't Panic"
    assert title_case("route 66 north") == "Route 66 North"


def test_trim_leading_and_trailing_whitespace_only():
    final, _, _ = run_advanced(cities(), text_plan(city=step(trim=True)))
    assert values(final["city"]) == ["new  york", "NEW YORK", "new york", "Paris", "paris"]


def test_collapse_repeated_spaces_only():
    final, _, _ = run_advanced(cities(), text_plan(city=step(collapse=True)))
    assert values(final["city"])[0] == " new york "                    # inner spaces collapsed, edges untouched


def test_all_text_operations_run_in_the_documented_order():
    final, rep, _ = run_advanced(cities(), text_plan(city=step(trim=True, collapse=True, case="title")))
    assert values(final["city"]) == ["New York", "New York", "New York", "Paris", "Paris"]
    assert rep["text_cells_changed"] == 4 and rep["columns_modified"] == 1


def test_find_and_replace_exact_text_not_patterns():
    df = frame(code=["a.c", "abc", "a.c a.c"], who=list("abc"))
    rule = {"find": "a.c", "replace": "X", "match_case": True, "whole_cell": False}
    final, _, _ = run_advanced(df, text_plan(code=step(replace=[rule])))
    assert values(final["code"]) == ["X", "abc", "X X"]                # "." is a dot, not "any character"


def test_find_and_replace_whole_cell_and_case_options():
    df = frame(c=["USA", "usa", "USA today", "Canada"])
    whole = {"find": "usa", "replace": "United States", "match_case": False, "whole_cell": True}
    assert values(run_advanced(df, text_plan(c=step(replace=[whole])))[0]["c"]) == \
        ["United States", "United States", "USA today", "Canada"]
    exact = {"find": "usa", "replace": "US", "match_case": True, "whole_cell": False}
    assert values(run_advanced(df, text_plan(c=step(replace=[exact])))[0]["c"]) == ["USA", "US", "USA today", "Canada"]


def test_find_and_replace_rules_run_top_to_bottom_and_replacement_is_literal():
    df = frame(c=["one two"], who=["x"])
    rules = [{"find": "one", "replace": "1", "match_case": False, "whole_cell": False},
             {"find": "two", "replace": r"\1$&", "match_case": False, "whole_cell": False}]
    assert values(run_advanced(df, text_plan(c=step(replace=rules)))[0]["c"]) == [r"1 \1$&"]


def test_a_cell_replaced_with_nothing_becomes_missing_and_is_reported():
    df = frame(c=["n.a.", "ok", "n.a."], who=list("abc"))
    rule = {"find": "n.a.", "replace": "", "match_case": False, "whole_cell": True}
    final, rep, _ = run_advanced(df, text_plan(c=step(replace=[rule])))
    assert values(final["c"]) == [None, "ok", None]
    assert rep["missing_final"] == 2 and any("empty" in w for w in rep["warnings"])


def test_missing_cells_are_never_turned_into_text():
    df = frame(c=["a", None, "b"], who=list("xyz"))
    final, _, _ = run_advanced(df, text_plan(c=step(case="upper", trim=True, collapse=True)))
    assert values(final["c"]) == ["A", None, "B"]


# ----------------------------------------------------------------------------- protection
def test_identifier_columns_are_protected():
    df = frame(customer_id=["C001", "C002", "C003", "C004"], who=list("abcd"))
    with pytest.raises(CleanSheetError, match="identifier column"):
        run_advanced(df, text_plan(customer_id=step(case="lower")))


def test_leading_zeros_in_identifier_columns_survive_other_text_changes():
    df = frame(zip=["00123", "00456", "01234", "09999"], city=[" a ", " b ", " c ", " d "])
    final, _, _ = run_advanced(df, text_plan(city=step(trim=True, case="upper")))
    assert values(final["zip"]) == ["00123", "00456", "01234", "09999"]


@pytest.mark.parametrize("name,cells", [("amount", ["1.5", "2.5", "3.5"]),
                                         ("order_date", ["2024-01-01", "2024-01-02", "2024-01-03"])])
def test_numeric_and_date_columns_never_get_text_casing(name, cells):
    df = frame(**{name: cells})
    with pytest.raises(CleanSheetError, match="only available for text columns"):
        run_advanced(df, text_plan(**{name: step(case="upper")}))


def test_text_options_are_offered_only_for_text_and_category_columns():
    from app.core import text as text_mod
    from app.core.profiling import profile_frame
    df = frame(customer=["Ann", "Bo", "Ann", "Bo"], customer_id=["C1", "C2", "C3", "C4"],
               amount=["1.5", "2.5", "3.5", "4.5"], when=["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    offered = [c["name"] for c in text_mod.describe_columns(df, profile_frame(df))]
    assert offered == ["customer"]


# ----------------------------------------------------------------------------- validation
def test_text_plan_validation():
    df = cities()
    with pytest.raises(CleanSheetError):
        run_advanced(df, text_plan(city=step(case="sideways")))
    with pytest.raises(CleanSheetError):
        run_advanced(df, text_plan(nope=step(case="lower")))
    too_many = [{"find": f"x{i}", "replace": "y", "match_case": False, "whole_cell": False} for i in range(11)]
    with pytest.raises(CleanSheetError, match="At most"):
        run_advanced(df, text_plan(city=step(replace=too_many)))
    long_rule = [{"find": "x" * 201, "replace": "", "match_case": False, "whole_cell": False}]
    with pytest.raises(CleanSheetError, match="too long"):
        run_advanced(df, text_plan(city=step(replace=long_rule)))


def test_blank_find_rows_are_ignored():
    final, rep, _ = run_advanced(cities(), text_plan(city=step(replace=[{"find": "", "replace": "x"}])))
    assert final.equals(cities()) and rep["empty_plan"] is True


def test_input_is_not_modified():
    df = cities()
    snapshot = df.copy()
    run_advanced(df, text_plan(city=step(case="upper", trim=True)))
    assert df.equals(snapshot)

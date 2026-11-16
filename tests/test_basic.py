"""Step 1: duplicates, whitespace, missing-value placeholders, binary columns."""
import pytest

from app.core.basic import apply_basic, clean_options, scan
from app.core.errors import CleanSheetError
from helpers import frame, values


def opts(**kw):
    base = {"remove_duplicates": False, "dedupe_mode": "all", "dedupe_columns": [], "trim": False,
            "normalise_missing": False, "binary": {}}
    base.update(kw)
    return clean_options(base)


# ----------------------------------------------------------------------------- duplicates
def test_duplicates_all_columns_keeps_first_copy():
    df = frame(a=["1", "2", "1", "3", "2"], b=["x", "y", "x", "z", "y"])
    out, rep = apply_basic(df, opts(remove_duplicates=True))
    assert list(out.index) == [0, 1, 3]
    assert (rep["original_rows"], rep["cleaned_rows"], rep["duplicates_removed"]) == (5, 3, 2)


def test_duplicates_selected_columns_only():
    df = frame(id=["1", "1", "2"], note=["a", "b", "c"])
    out, rep = apply_basic(df, opts(remove_duplicates=True, dedupe_mode="subset", dedupe_columns=["id"]))
    assert list(out.index) == [0, 2] and rep["duplicates_removed"] == 1
    out_all, rep_all = apply_basic(df, opts(remove_duplicates=True))          # all columns: nothing repeats
    assert len(out_all) == 3 and rep_all["duplicates_removed"] == 0


def test_duplicates_not_removed_unless_asked():
    df = frame(a=["1", "1"])
    out, rep = apply_basic(df, opts(remove_duplicates=False))
    assert len(out) == 2 and rep["duplicates_removed"] == 0


def test_duplicate_rows_with_missing_cells_match_each_other():
    df = frame(a=["1", "1"], b=[None, None])
    out, _ = apply_basic(df, opts(remove_duplicates=True))
    assert len(out) == 1


@pytest.mark.parametrize("bad", [
    {"dedupe_mode": "subset", "dedupe_columns": []},
    {"dedupe_mode": "subset", "dedupe_columns": ["nope"]},
    {"dedupe_mode": "everything"},
])
def test_duplicate_options_are_validated(bad):
    df = frame(a=["1", "1"])
    with pytest.raises(CleanSheetError):
        apply_basic(df, opts(remove_duplicates=True, **bad))


def test_options_with_wrong_shape_are_rejected():
    with pytest.raises(CleanSheetError):
        clean_options({"dedupe_columns": "a"})
    with pytest.raises(CleanSheetError):
        clean_options({"binary": ["a"]})
    with pytest.raises(CleanSheetError):
        clean_options("nonsense")


# ----------------------------------------------------------------------------- whitespace
def test_trim_counts_only_cells_that_changed():
    df = frame(name=["  Ann ", "Bo", None, "\tCy\n"], city=["Pune", " Delhi", "Pune", "Pune"])
    out, rep = apply_basic(df, opts(trim=True))
    assert values(out["name"]) == ["Ann", "Bo", None, "Cy"]
    assert values(out["city"]) == ["Pune", "Delhi", "Pune", "Pune"]
    assert rep["whitespace_cells_changed"] == 3 and rep["whitespace_columns_changed"] == 2


def test_trim_runs_before_duplicate_matching():
    df = frame(name=["Ann ", "Ann", "Bo"])
    out, rep = apply_basic(df, opts(trim=True, remove_duplicates=True))
    assert values(out["name"]) == ["Ann", "Bo"] and rep["duplicates_removed"] == 1


def test_trim_keeps_internal_spaces():
    out, _ = apply_basic(frame(a=["  a  b  "]), opts(trim=True))
    assert values(out["a"]) == ["a  b"]


# ----------------------------------------------------------------------------- missing placeholders
def test_placeholders_become_missing_but_real_values_do_not():
    cells = ["N/A", "n/a", " NULL ", "-", "", "none", "?", "NaN", "ok", "0", "No", "unknown"]
    out, rep = apply_basic(frame(a=cells), opts(normalise_missing=True))
    assert values(out["a"]) == [None] * 8 + ["ok", "0", "No", "unknown"]
    assert rep["missing_tokens_normalised"] == 8          # 7 placeholder words/symbols + the empty-string cell
    assert rep["missing_after"] == 8


def test_existing_blanks_are_counted_before_and_after():
    df = frame(a=["x", None, "N/A"])
    _, rep = apply_basic(df, opts(normalise_missing=True))
    assert (rep["missing_before"], rep["missing_after"]) == (1, 2)


def test_placeholders_untouched_when_option_is_off():
    out, _ = apply_basic(frame(a=["N/A"]), opts(normalise_missing=False))
    assert values(out["a"]) == ["N/A"]


# ----------------------------------------------------------------------------- binary columns
def test_binary_columns_are_detected():
    df = frame(a=["Yes", "No", "Yes"], b=["TRUE", "FALSE", None], c=["1", "0", "1"], d=["Y", "N", "Y"],
               e=["x", "y", "z"], f=["Yes", "No", "Maybe"])
    found = {b["name"]: b["style"] for b in scan(df)["binary_columns"]}
    assert found == {"a": "Yes/No", "b": "TRUE/FALSE", "c": "1/0", "d": "Y/N"}


def test_binary_columns_convert_independently():
    df = frame(returned=["Yes", "No", "yes"], flag=["TRUE", "FALSE", "true"], news=["1", "0", "1"],
               other=["Yes", "No", "Yes"])
    out, rep = apply_basic(df, opts(binary={"returned": "true_false", "flag": "yes_no", "news": "yes_no"}))
    assert values(out["returned"]) == ["TRUE", "FALSE", "TRUE"]
    assert values(out["flag"]) == ["Yes", "No", "Yes"]
    assert values(out["news"]) == ["Yes", "No", "Yes"]
    assert values(out["other"]) == ["Yes", "No", "Yes"]                # not selected: untouched
    assert (rep["binary_detected"], rep["binary_converted"]) == (4, 3)


def test_binary_to_one_zero_and_gaps_stay_gaps():
    df = frame(a=["Yes", None, "No", "Y", "n"])
    out, _ = apply_basic(df, opts(binary={"a": "one_zero"}))
    assert values(out["a"]) == ["1", None, "0", "1", "0"]


def test_column_with_only_ones_is_a_number_not_a_flag():
    assert scan(frame(a=["1", "1", "1"]))["binary_columns"] == []


def test_one_zero_columns_are_flagged_as_possibly_numeric():
    found = scan(frame(a=["1", "0", "1"]))["binary_columns"]
    assert found[0]["numeric_only"] is True
    assert scan(frame(a=["Yes", "No"]))["binary_columns"][0]["numeric_only"] is False


def test_binary_choices_are_validated():
    df = frame(a=["Yes", "No"])
    with pytest.raises(CleanSheetError):
        apply_basic(df, opts(binary={"a": "maybe"}))
    with pytest.raises(CleanSheetError):
        apply_basic(df, opts(binary={"missing_column": "yes_no"}))


# ----------------------------------------------------------------------------- purity
def test_original_is_never_modified_and_reapplying_is_stable():
    df = frame(a=[" Yes ", "No", " Yes "], b=["N/A", "x", "x"])
    snapshot = df.copy()
    o = opts(trim=True, normalise_missing=True, remove_duplicates=True, binary={"a": "true_false"})
    first, rep1 = apply_basic(df, o)
    second, rep2 = apply_basic(df, o)
    assert df.equals(snapshot)
    assert first.equals(second) and rep1 == rep2


def test_scan_reports_what_cleaning_would_find():
    df = frame(a=["x ", "x", "N/A", "y"], b=["1", "1", "2", "3"])
    s = scan(df)
    assert s["whitespace_cells"] == 1 and s["missing_token_cells"] == 1 and s["duplicate_rows"] == 1

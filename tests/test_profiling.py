"""Rule-based column detection: names AND values decide; uncertainty is surfaced, never guessed away."""
import pytest

from app.core.profiling import profile_frame
from helpers import frame, profiles_of


def kind(df, name, **kw):
    return profiles_of(df, **kw)[name]["kind"]


# ----------------------------------------------------------------------------- the examples in the brief
def test_customer_id_is_an_identifier():
    assert kind(frame(customer_id=["C001", "C002", "C001", "C003"]), "customer_id") == "identifier"
    assert kind(frame(customer_id=["1001", "1002", "1003", "1004"]), "customer_id") == "identifier"


def test_order_date_is_a_date():
    df = frame(order_date=["2024-01-05", "2024-02-11", "2024-03-20"])
    p = profiles_of(df)["order_date"]
    assert p["kind"] == "date" and p["date_format"] == "%Y-%m-%d"


def test_customer_is_categorical_text():
    df = frame(customer=["Ann Lee", "Bo Chen", "Ann Lee", "Cy Diaz", "Bo Chen", "Ann Lee"])
    assert kind(df, "customer") == "categorical"


def test_free_text_with_many_distinct_values_is_text():
    df = frame(comment=[f"customer wrote something unique number {i}" for i in range(60)])
    assert kind(df, "comment") == "text"


def test_revenue_is_calculated_when_it_follows_a_formula():
    df = frame(quantity=["1", "2", "3", "4", "5", "6", "7"],
               unit_price=["2.50", "4.00", "3.00", "5.50", "2.00", "9.00", "1.50"],
               revenue=["2.50", "8.00", "9.00", "22.00", "10.00", "54.00", "10.50"])
    p = profiles_of(df)["revenue"]
    assert p["kind"] == "calculated"
    assert p["formulas"][0]["label"] in ("revenue = quantity × unit_price", "revenue = unit_price × quantity")


# ----------------------------------------------------------------------------- names alone never decide
def test_a_date_name_with_non_date_values_is_not_a_date():
    assert kind(frame(order_date=["Ann", "Bo", "Cy", "Ann"]), "order_date") != "date"
    assert kind(frame(order_date=["1", "2", "3", "4", "5"]), "order_date") == "numeric"


def test_an_id_name_with_decimal_values_is_not_silently_an_identifier():
    p = profiles_of(frame(price_id=["1.5", "2.25", "3.75", "4.5"]))["price_id"]
    assert p["kind"] == "numeric" and p["needs_confirmation"] is True and "identifier" in p["alternatives"]


def test_a_revenue_name_without_a_formula_is_just_a_number():
    df = frame(revenue=["10", "20", "35", "7"], other=["a", "b", "c", "d"])
    assert kind(df, "revenue") == "numeric"


def test_a_revenue_name_with_text_values_stays_text():
    assert kind(frame(revenue=["high", "low", "medium", "low"]), "revenue") == "categorical"


def test_an_unremarkable_name_with_code_values_is_still_an_identifier():
    df = frame(x=[f"AB-{i:04d}" for i in range(20)])
    assert kind(df, "x") == "identifier"


def test_leading_zero_digits_are_an_identifier_whatever_the_name():
    p = profiles_of(frame(zipish=["00123", "00456", "01234", "09999"]))["zipish"]
    assert p["kind"] == "identifier" and p["leading_zeros"] is True


# ----------------------------------------------------------------------------- other kinds
@pytest.mark.parametrize("cells", [["Yes", "No", "Yes", "No"], ["TRUE", "FALSE", "TRUE"], ["Y", "N", "Y", "N"]])
def test_two_state_columns_are_boolean(cells):
    p = profiles_of(frame(whatever=cells))["whatever"]
    assert p["kind"] == "boolean" and p["needs_confirmation"] is False


def test_plain_numbers_are_numeric_with_thousands_separators_allowed():
    p = profiles_of(frame(amount=["1,200", "950.50", "3,400.25", "12"]))["amount"]
    assert p["kind"] == "numeric" and p["max_decimals"] == 2


def test_empty_column_is_text_and_does_not_crash():
    p = profiles_of(frame(a=[None, None, None]))["a"]
    assert p["kind"] == "text" and p["missing"] == 3 and p["non_missing"] == 0


def test_every_profile_explains_itself():
    df = frame(a=["x", "y", "x"], b=["1", "2", "3"], c=["2024-01-01", "2024-01-02", "2024-01-03"])
    for p in profile_frame(df):
        assert p["reasons"] and p["kind_label"] and p["confidence"] in ("high", "medium", "low")


# ----------------------------------------------------------------------------- uncertainty is surfaced
def test_only_ones_and_zeros_ask_the_user_to_confirm():
    p = profiles_of(frame(count=["1", "0", "1", "0"]))["count"]
    assert p["needs_confirmation"] is True and "numeric" in p["alternatives"]
    flag = profiles_of(frame(is_active=["1", "0", "1", "0"]))["is_active"]
    assert flag["needs_confirmation"] is False                 # the name AND the values agree


def test_a_confirmation_from_the_user_settles_the_type():
    df = frame(count=["1", "0", "1", "0"])
    p = profiles_of(df, overrides={"count": "numeric"})["count"]
    assert p["kind"] == "numeric" and p["confirmed"] is True and p["needs_confirmation"] is False


def test_mostly_dates_under_a_date_name_asks_instead_of_guessing():
    df = frame(created=["2024-01-05", "2024-02-06", "soon", "2024-03-07", "later"])
    p = profiles_of(df)["created"]
    assert p["kind"] == "date" and p["needs_confirmation"] is True and "text" in p["alternatives"]


def test_mostly_dates_asks_even_when_the_name_gives_no_hint():
    """Numbers already ask when 50-90% of the values fit; dates must too. 8 dates and one date-with-time in a column
    called 'signup' used to be called a high-confidence category, silently."""
    df = frame(signup=["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06",
                       "2024-01-07", "2024-01-08", "2024-02-03 14:30:00"])
    p = profiles_of(df)["signup"]
    assert p["kind"] == "date" and p["needs_confirmation"] is True and "text" in p["alternatives"]
    assert "look like dates" in p["reasons"][0] and "name" not in p["reasons"][0]
    confirmed = profiles_of(df, overrides={"signup": "text"})["signup"]            # the person can say it is text
    assert confirmed["kind"] == "text" and confirmed["confirmed"] is True


def test_a_column_that_is_mostly_text_with_one_date_is_not_asked_about():
    p = profiles_of(frame(remark=["2024-01-05", "ann", "bo", "cy", "di", "ed"]))["remark"]
    assert p["kind"] in ("text", "categorical") and p["needs_confirmation"] is False


def test_clean_dates_are_still_confident_without_asking():
    p = profiles_of(frame(signup=["2024-01-01", "2024-01-02", "2024-01-03"]))["signup"]
    assert p["kind"] == "date" and p["needs_confirmation"] is False


def test_day_month_order_is_ambiguous_until_the_data_settles_it():
    amb = profiles_of(frame(d=["03/04/2024", "05/06/2024", "07/08/2024"]))["d"]
    assert amb["date_ambiguous"] is True and set(amb["date_candidates"]) == {"%d/%m/%Y", "%m/%d/%Y"}
    day_first = profiles_of(frame(d=["03/04/2024", "25/06/2024"]))["d"]
    assert day_first["date_ambiguous"] is False and day_first["date_format"] == "%d/%m/%Y"
    month_first = profiles_of(frame(d=["03/04/2024", "06/25/2024"]))["d"]
    assert month_first["date_format"] == "%m/%d/%Y"


def test_the_users_day_month_choice_resolves_the_ambiguity():
    df = frame(d=["03/04/2024", "05/06/2024"])
    p = profiles_of(df, date_formats={"d": "%m/%d/%Y"})["d"]
    assert p["date_ambiguous"] is False and p["date_format"] == "%m/%d/%Y"

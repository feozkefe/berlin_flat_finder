from datetime import date, timedelta

from app.dates import (
    extract_date_range,
    extract_duration_months,
    fill_timing,
    months_between,
    parse_available_from,
    parse_user_months,
    parse_user_start,
    timing_passes,
)
from app.models import Filters, Listing
from app.scanner import listing_passes


def test_parse_start_and_months():
    assert parse_user_start("0") == ""
    assert parse_user_start("01.10.2026") == "2026-10-01"
    assert parse_user_start("xyz") == "invalid"
    assert parse_user_months("0") == (1, 0)
    assert parse_user_months("1") == (1, 0)
    assert parse_user_months("1 ay") == (1, 0)
    assert parse_user_months("1 month") == (1, 0)
    assert parse_user_months("6") == (6, 0)
    assert parse_user_months("6-12") == (6, 12)


def test_german_month_plurals_are_durations():
    assert extract_duration_months("Mindestmietdauer 6 Monate") == 6
    assert extract_duration_months("Vermietung für 3 Monaten") == 3
    assert extract_duration_months("Sublet for 4 months") == 4


def test_deposit_in_months_is_not_a_duration():
    assert extract_duration_months("Kaution 3 Monatsmieten") is None
    assert extract_duration_months("Kaution: 2 Monate") is None


def test_move_in_date_needs_an_availability_cue():
    soon = date.today() + timedelta(days=30)
    stamp = soon.strftime("%d.%m.%Y")
    assert parse_available_from(f"Frei ab {stamp}") == soon
    assert parse_available_from(f"Sanierte Wohnung zum {stamp}!") == soon
    assert parse_available_from("Ab sofort zu vergeben") == date.today()
    # A bare date in the ad copy is not a move-in date.
    assert parse_available_from("Neubau aus dem Jahr 1970, saniert 12.05.2019") is None


def test_year_less_dates_resolve_forward():
    found = parse_available_from("WG Zimmer ab 1.10 frei")
    assert found is not None and (found.month, found.day) == (10, 1)
    assert found >= date.today() - timedelta(days=45)


def test_sublet_window_gives_start_end_and_length():
    start = date.today() + timedelta(days=20)
    end = start + timedelta(days=60)
    window = extract_date_range(f"Zwischenmiete {start:%d.%m.%Y}-{end:%d.%m.%Y}")
    assert window == (start, end)
    # 01.10.-30.11. spans two months, not one.
    assert months_between(date(2026, 10, 1), date(2026, 11, 30)) == 2


def test_fill_timing_ignores_dates_without_a_cue():
    listing = Listing(id="1", provider="kleinanzeigen", title="Altbau von 1904", url="u")
    fill_timing(listing, extra_text="Renoviert am 03.04.2021. Kaution 3 Monatsmieten.")
    assert listing.available_from is None
    assert listing.duration_months is None


def test_fill_timing_reads_a_sublet_window():
    start = date.today() + timedelta(days=20)
    end = start + timedelta(days=91)
    listing = Listing(
        id="2",
        provider="kleinanzeigen",
        title=f"Zwischenmiete {start:%d.%m.%Y}-{end:%d.%m.%Y}",
        url="u",
    )
    fill_timing(listing)
    assert listing.available_from == start.strftime("%d.%m.%Y")
    assert listing.available_to == end.strftime("%d.%m.%Y")
    assert listing.duration_months == 3


def test_start_from_drops_late_listings():
    filters = Filters(start_from="2026-10-01", listing_types=["apartment"], districts=[])
    late = Listing(id="1", provider="wg_gesucht", title="Daire", url="u", address="Neukölln", available_from="01.12.2026")
    ok = Listing(id="2", provider="wg_gesucht", title="Daire", url="u", address="Neukölln", available_from="15.09.2026")
    unknown = Listing(id="3", provider="wg_gesucht", title="Daire", url="u", address="Neukölln")
    assert not listing_passes(late, filters)
    assert listing_passes(ok, filters)
    assert listing_passes(unknown, filters)


def test_min_months_drops_short_sublet():
    filters = Filters(min_months=6, listing_types=["apartment", "sublet"], districts=[])
    short = Listing(id="1", provider="wg_gesucht", title="3 Monate", url="u", address="Mitte", duration_months=3, is_sublet=True)
    long = Listing(id="2", provider="wg_gesucht", title="12 Monate", url="u", address="Mitte", duration_months=12, is_sublet=True)
    assert not listing_passes(short, filters)
    assert listing_passes(long, filters)


def test_max_months_drops_unlimited():
    listing = Listing(id="1", provider="wg_gesucht", title="Unbefristet", url="u", address="Mitte")
    assert not timing_passes(listing, "", 0, 6)
    listing.duration_months = 4
    assert timing_passes(listing, "", 0, 6)
    listing.available_from = (date.today() + timedelta(days=40)).strftime("%d.%m.%Y")
    assert not timing_passes(listing, date.today().isoformat(), 0, 0)


def test_start_filter_drops_listings_that_start_much_earlier():
    listing = Listing(id="x", provider="wg_gesucht", title="Zimmer", url="u")
    wanted = date.today() + timedelta(days=70)
    listing.available_from = (wanted - timedelta(days=60)).strftime("%d.%m.%Y")
    assert not timing_passes(listing, wanted.isoformat(), 0, 0)
    listing.available_from = (wanted - timedelta(days=7)).strftime("%d.%m.%Y")
    assert timing_passes(listing, wanted.isoformat(), 0, 0)

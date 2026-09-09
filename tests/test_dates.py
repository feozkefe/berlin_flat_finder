from datetime import date, timedelta

from app.dates import parse_user_months, parse_user_start, timing_passes
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

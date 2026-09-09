from app.models import Filters, Listing
from app.scanner import listing_passes, rank


def test_filters_rent_and_wbs():
    filters = Filters(max_rent=1000, districts=["neukoelln"], listing_types=["apartment"], exclude_keywords=["wbs"])
    ok = Listing(
        id="1",
        provider="kleinanzeigen",
        title="2 Zi Neukölln",
        url="u",
        price=950,
        rooms=2,
        address="Neukölln",
        district="Neukölln",
        postcode="12047",
    )
    expensive = Listing(**{**ok.to_dict(), "id": "2", "price": 1400})
    wbs = Listing(**{**ok.to_dict(), "id": "3", "title": "2 Zi Neukölln nur mit WBS erforderlich"})
    assert listing_passes(ok, filters)
    assert not listing_passes(expensive, filters)
    assert not listing_passes(wbs, filters)


def test_negated_exclusion_keeps_the_ad():
    filters = Filters(max_rent=1000, districts=[], listing_types=["apartment"], exclude_keywords=["wbs"])
    good = Listing(id="1", provider="kleinanzeigen", title="2 Zi, ohne WBS", url="u", price=900, rooms=2)
    assert listing_passes(good, filters)


def test_min_rooms_does_not_drop_wg_rooms():
    # A WG ad is one room in someone else's flat; its room count is not comparable.
    filters = Filters(min_rooms=2, listing_types=["wg"], districts=[])
    room = Listing(
        id="1",
        provider="wg_gesucht",
        title="Zimmer in 3er WG",
        url="u",
        price=550,
        rooms=None,
        size_sqm=15,
        listing_kind="wg",
        flatmates=2,
    )
    assert listing_passes(room, filters)


def test_min_rooms_still_applies_to_apartments():
    filters = Filters(min_rooms=2, listing_types=["apartment"], districts=[])
    small = Listing(id="1", provider="immoscout", title="1 Zi", url="u", price=800, rooms=1)
    assert not listing_passes(small, filters)


def test_wg_type_filter_uses_listing_kind():
    room = Listing(id="1", provider="wg_gesucht", title="Zimmer", url="u", listing_kind="wg")
    flat = Listing(id="2", provider="wg_gesucht", title="Wohnung", url="u", listing_kind="apartment", rooms=2)
    assert listing_passes(room, Filters(listing_types=["wg"], districts=[]))
    assert not listing_passes(flat, Filters(listing_types=["wg"], districts=[]))
    assert listing_passes(flat, Filters(listing_types=["apartment"], districts=[]))
    assert not listing_passes(room, Filters(listing_types=["apartment"], districts=[]))


def test_sublet_only():
    filters = Filters(listing_types=["sublet"], districts=[])
    sub = Listing(id="1", provider="wg_gesucht", title="Zwischenmiete Mitte", url="u", is_sublet=True, address="Mitte")
    long_term = Listing(id="2", provider="wg_gesucht", title="Unbefristet Mitte", url="u", is_sublet=False, address="Mitte")
    assert listing_passes(sub, filters)
    assert not listing_passes(long_term, filters)


def test_sublets_are_excluded_when_not_requested():
    filters = Filters(listing_types=["apartment"], districts=[])
    sub = Listing(id="1", provider="wg_gesucht", title="Zwischenmiete", url="u", is_sublet=True, rooms=2)
    assert not listing_passes(sub, filters)


def test_rank_puts_messageable_listings_first():
    view_only = Listing(id="1", provider="immoscout", title="a", url="u", contactable=False, price=700)
    agency = Listing(id="2", provider="kleinanzeigen", title="b", url="u", contactable=True, price=900)
    private = Listing(
        id="3", provider="wg_gesucht", title="c", url="u", contactable=True, price=950, private_landlord=True
    )
    assert [item.id for item in rank([view_only, agency, private])] == ["3", "2", "1"]


def test_rank_treats_a_cross_posted_immoscout_ad_as_messageable():
    crossposted = Listing(
        id="1",
        provider="immoscout",
        title="a",
        url="u",
        contactable=False,
        price=700,
        alt_urls=[{"provider": "kleinanzeigen", "url": "https://k/1", "title": "a"}],
    )
    view_only = Listing(id="2", provider="immoscout", title="b", url="u", contactable=False, price=600)
    assert [item.id for item in rank([view_only, crossposted])] == ["1", "2"]

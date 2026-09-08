from app.models import Filters, Listing
from app.scanner import listing_passes


def test_filters_rent_and_wbs():
    filters = Filters(max_rent=1000, districts=["neukoelln"], listing_types=["apartment"], exclude_keywords=["wbs erforderlich"])
    ok = Listing(
        id="1",
        provider="kleinanzeigen",
        title="2 Zi Neukölln",
        url="u",
        price=950,
        rooms=2,
        address="Neukölln",
        district="Neukölln",
    )
    expensive = Listing(**{**ok.to_dict(), "id": "2", "price": 1400})
    wbs = Listing(**{**ok.to_dict(), "id": "3", "title": "2 Zi Neukölln nur mit WBS erforderlich"})
    assert listing_passes(ok, filters)
    assert not listing_passes(expensive, filters)
    assert not listing_passes(wbs, filters)


def test_sublet_only():
    filters = Filters(listing_types=["sublet"], districts=[])
    sub = Listing(id="1", provider="wg_gesucht", title="Zwischenmiete Mitte", url="u", is_sublet=True, address="Mitte")
    long_term = Listing(id="2", provider="wg_gesucht", title="Unbefristet Mitte", url="u", is_sublet=False, address="Mitte")
    assert listing_passes(sub, filters)
    assert not listing_passes(long_term, filters)

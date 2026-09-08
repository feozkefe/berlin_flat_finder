from app.matching import looks_like_sublet, looks_like_wanted_ad, normalize_street, same_listing
from app.models import Listing


def test_same_listing_by_street_and_price():
    left = Listing(
        id="is24_1",
        provider="immoscout",
        title="Altbau",
        url="https://immoscout/1",
        price=980,
        rooms=2,
        size_sqm=54,
        address="Danziger Straße 12, 10405 Berlin",
        contactable=False,
    )
    right = Listing(
        id="ka_9",
        provider="kleinanzeigen",
        title="2 Zi Prenzlauer Berg",
        url="https://kleinanzeigen/9",
        price=990,
        rooms=2,
        size_sqm=52,
        address="Danziger Str. 12, Prenzlauer Berg",
        contactable=True,
    )
    assert normalize_street(left.address)
    assert same_listing(left, right)


def test_different_streets_do_not_match():
    left = Listing(id="a", provider="immoscout", title="x", url="u", price=900, address="Weserstraße 1, 12047 Berlin")
    right = Listing(id="b", provider="kleinanzeigen", title="y", url="v", price=900, address="Warschauer Straße 1, 10243 Berlin")
    assert not same_listing(left, right)


def test_sublet_and_wanted_detection():
    assert looks_like_sublet("Befristete Zwischenmiete bis Juli")
    assert looks_like_wanted_ad("Suche 2-Zimmer Wohnung in Neukölln")
    assert not looks_like_wanted_ad("Helle 2-Zimmer Wohnung in Neukölln")

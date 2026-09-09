from app.sources.kleinanzeigen import _is_housing_ad


def test_keeps_apartment_category_url():
    assert _is_housing_ad(
        "https://www.kleinanzeigen.de/s-anzeige/2-zimmer-wohnung/123-203-3331",
        "2 Zimmer Wohnung Neukölln",
        "55 m²",
        "203",
    )


def test_drops_furniture_and_other_categories():
    assert not _is_housing_ad(
        "https://www.kleinanzeigen.de/s-anzeige/ikea-sofa/123-80-3331",
        "IKEA Sofa zu verkaufen",
        "Couch gut erhalten",
        "203",
    )
    assert not _is_housing_ad(
        "https://www.kleinanzeigen.de/s-anzeige/schrankwand/999-72-3331",
        "Schrankwand",
        "zu verschenken",
        "203",
    )

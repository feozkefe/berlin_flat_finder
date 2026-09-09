from app.sources.kleinanzeigen import KleinanzeigenSource, _is_housing_ad


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


def test_drops_wanted_ads():
    assert not _is_housing_ad(
        "https://www.kleinanzeigen.de/s-anzeige/ich-suche-eine-wohnung/350-203-3423",
        "Ich Suche eine Wohnung in Dresden oder in der Nähe davon",
        "Gesuch · 30 m² · 1 Zi.",
        "203",
    )


# Trimmed copy of a live result card. The site moved to utility classes, so the
# old .aditem-main--* selectors matched nothing and the title resolved to the
# image-count badge ("3") instead of the headline.
CARD = """
<article data-adid="3506770638"
         data-href="/s-anzeige/sanierte-2-zimmerwohnng/3506770638-203-3388">
  <div>
    <a href="/s-anzeige/sanierte-2-zimmerwohnng/3506770638-203-3388">
      <div data-image-container>
        <img src="https://img.kleinanzeigen.de/api/v1/prod-ads/images/af/x.jpg" alt="Vorschau"/>
        <div>3</div>
      </div>
    </a>
  </div>
  <div>
    <div class="text-onSurfaceNonessential"><span>12353 Neukölln</span></div>
    <div>
      <h3><a href="/s-anzeige/sanierte-2-zimmerwohnng/3506770638-203-3388">Sanierte 2-Zimmerwohnng frei ab 01.10.2026!</a></h3>
      <p class="mb-xsmall text-bodyRegular text-onSurfaceSubdued">Neubau aus dem Jahr 1970. Kaution 3 Monatsmieten...</p>
      <p class="font-strong text-onSurfaceSubdued">74,08 m² · 2 Zi.</p>
      <div><p class="my-xsmall text-title3 font-strong text-secondary">822 €</p></div>
      <p>Von Privat</p>
    </div>
  </div>
</article>
"""


def _only(html: str, cat_id: str = "203", kind: str = "apartment"):
    found = KleinanzeigenSource()._parse(html, cat_id, kind)
    assert len(found) == 1
    return found[0]


def test_parses_current_markup():
    listing = _only(CARD)
    assert listing.title == "Sanierte 2-Zimmerwohnng frei ab 01.10.2026!"
    assert listing.url.endswith("/s-anzeige/sanierte-2-zimmerwohnng/3506770638-203-3388")
    assert listing.price == 822.0
    assert listing.size_sqm == 74.08
    assert listing.rooms == 2.0
    assert listing.postcode == "12353"
    assert listing.district == "Neukölln"
    assert listing.private_landlord is True


def test_reads_move_in_date_and_ignores_unrelated_years():
    listing = _only(CARD)
    assert listing.available_from == "01.10.2026"
    # "Kaution 3 Monatsmieten" is a deposit, not a tenancy length.
    assert listing.duration_months is None


def test_wg_room_count_describes_the_flat_not_the_room():
    listing = _only(CARD.replace("-203-", "-199-"), cat_id="199", kind="wg")
    assert listing.listing_kind == "wg"
    assert listing.rooms is None
    assert listing.flat_rooms == 2.0


def test_drops_non_berlin_and_junk_priced_ads():
    assert not KleinanzeigenSource()._parse(CARD.replace("12353 Neukölln", "01067 Dresden"), "203", "apartment")
    assert not KleinanzeigenSource()._parse(CARD.replace("822 €", "1 €"), "203", "apartment")

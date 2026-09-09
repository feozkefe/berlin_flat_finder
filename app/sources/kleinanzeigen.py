from __future__ import annotations

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.dates import fill_timing
from app.districts import detect_district, extract_plz, is_berlin_plz
from app.matching import looks_like_sublet, looks_like_wanted_ad
from app.models import Filters, Listing
from app.sources.base import BROWSER_HEADERS, BaseSource

logger = logging.getLogger(__name__)

BASE = "https://www.kleinanzeigen.de"
# 203 = Wohnung mieten, 199 = WG / auf Zeit. Slug must match the live site.
CATEGORIES = {
    "apartment": ("wohnung-mieten", "c203", "203"),
    "wg": ("wg-zimmer", "c199", "199"),
}
_JUNK = (
    "zu verschenken",
    "kühlschrank",
    "kuehlschrank",
    "schrankwand",
    "couch",
    "sofa",
    "kommode",
    "esstisch",
    "tv board",
    "tv-board",
    "waschmaschine",
)
# Ads placed by someone *looking* for a flat, not offering one.
_WANTED_MARKERS = ("gesuch", "suche wohnung", "suche zimmer", "wohnung gesucht", "zimmer gesucht")

# Sanity bounds. Kleinanzeigen lets posters type anything into the attribute
# fields, and the WG category is full of stray furniture ads priced at 1 €.
_MIN_PRICE = 100.0
_MAX_SIZE = 400.0
_MIN_SIZE = 5.0
_MAX_ROOMS = 12.0


class KleinanzeigenSource(BaseSource):
    name = "kleinanzeigen"

    async def search(self, client: httpx.AsyncClient, filters: Filters) -> list[Listing]:
        listings: list[Listing] = []
        seen: set[str] = set()
        kinds = []
        if "wg" in filters.listing_types:
            kinds.append("wg")
        if any(t in filters.listing_types for t in ("apartment", "sublet")):
            kinds.append("apartment")
        budget = max(8, settings.max_listings_per_source // max(1, len(kinds)))

        for kind in kinds:
            slug, code, cat_id = CATEGORIES[kind]
            taken = 0
            for page in range(1, settings.max_pages_per_source + 1):
                url = self._search_url(slug, code, filters, page)
                try:
                    response = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("Kleinanzeigen search failed url=%s: %s", url, exc)
                    break

                page_listings = self._parse(response.text, cat_id, kind)
                if not page_listings:
                    break
                for listing in page_listings:
                    if listing.id in seen:
                        continue
                    listings.append(listing)
                    seen.add(listing.id)
                    taken += 1
                    if taken >= budget:
                        break
                if taken >= budget:
                    break

        return listings

    def _search_url(self, slug: str, code: str, filters: Filters, page: int) -> str:
        path = f"/s-{slug}/berlin/preis:0:{filters.max_rent}"
        if page > 1:
            path += f"/seite:{page}"
        return f"{BASE}{path}/{code}l3331"

    def _parse(self, html: str, cat_id: str, kind: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        listings: list[Listing] = []

        for article in soup.select("article[data-adid]"):
            listing = self._parse_article(article, cat_id, kind)
            if listing:
                listings.append(listing)
        return listings

    def _parse_article(self, article, cat_id: str, kind: str) -> Listing | None:
        ad_id = article.get("data-adid")
        if not ad_id:
            return None

        seed = _ld_json(article)
        title = _title(article) or (seed.get("title") or "").strip()
        if not title:
            return None

        href = article.get("data-href") or ""
        if not href:
            link = article.select_one("h3 a[href], a[href*='/s-anzeige/']")
            href = link.get("href", "") if link else ""
        if not href:
            return None
        url = href if href.startswith("http") else f"{BASE}{href}"

        description = _description(article) or (seed.get("description") or "")
        tags = _tags(article)
        blob = f"{title} {description} {' '.join(tags)}"
        if not _is_housing_ad(url, title, blob, cat_id):
            return None

        location = _location(article)
        postcode = extract_plz(location) or ""
        if location and not is_berlin_plz(postcode):
            # The Berlin search leaks nationwide "Gesuch" ads (Dresden, Hamburg...).
            return None

        price = _price(article)
        if price is not None and price < _MIN_PRICE:
            return None

        size, rooms = _attributes(article)
        district = detect_district(f"{title} {location}", postcode)

        # In the WG category the m²/Zi. fields describe the whole flat, not the room.
        flat_rooms = rooms if kind == "wg" else None
        listing = Listing(
            id=f"ka_{ad_id}",
            provider="kleinanzeigen",
            title=title,
            url=url,
            price=price,
            rooms=None if kind == "wg" else rooms,
            size_sqm=size,
            address=location or "Berlin",
            district=district.name if district else "",
            postcode=postcode,
            listing_kind=kind,
            flat_rooms=flat_rooms,
            image_url=_image(article, seed),
            is_sublet=looks_like_sublet(blob),
            contactable=True,
            private_landlord=any("privat" in tag.lower() for tag in tags),
        )
        return fill_timing(listing, extra_text=f"{description} {' '.join(tags)}")


def _ld_json(article) -> dict:
    node = article.find("script", attrs={"type": "application/ld+json"})
    if not node or not node.string:
        return {}
    try:
        data = json.loads(node.string)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _title(article) -> str:
    node = article.select_one("h3 a, h2 a")
    return node.get_text(" ", strip=True) if node else ""


def _description(article) -> str:
    node = article.select_one("p.text-bodyRegular")
    return node.get_text(" ", strip=True) if node else ""


def _location(article) -> str:
    """The '12353 Neukölln' line above the title."""
    node = article.select_one("div.text-onSurfaceNonessential span")
    if node:
        return node.get_text(" ", strip=True)
    for span in article.select("span"):
        text = span.get_text(" ", strip=True)
        if re.match(r"^\d{5}\s+\S", text):
            return text
    return ""


def _tags(article) -> list[str]:
    return [p.get_text(" ", strip=True) for p in article.select("p") if p.get_text(strip=True)]


def _image(article, seed: dict) -> str | None:
    node = article.find("img")
    src = node.get("src") or node.get("data-src") if node else None
    src = src or seed.get("contentUrl")
    return src if src and str(src).startswith("http") else None


def _price(article) -> float | None:
    """Price element only. The description often quotes other amounts."""
    node = article.select_one("p.text-title3.font-strong.text-secondary")
    if node is None:
        for candidate in article.select("p"):
            text = candidate.get_text(" ", strip=True)
            if re.fullmatch(r"[\d.,]+\s*€(?:\s*VB)?", text):
                node = candidate
                break
    if node is None:
        return None
    return _parse_price(node.get_text(" ", strip=True))


def _attributes(article) -> tuple[float | None, float | None]:
    """Reads the '74,08 m² · 2 Zi.' line. Returns (size_sqm, rooms)."""
    for node in article.select("p"):
        text = node.get_text(" ", strip=True)
        if "m²" not in text and "Zi." not in text:
            continue
        size = _extract_number(text, r"(\d+(?:[.,]\d+)?)\s*m[²2]")
        rooms = _extract_number(text, r"(\d+(?:[.,]\d+)?)\s*Zi\.?")
        if size is not None and not _MIN_SIZE <= size <= _MAX_SIZE:
            size = None
        if rooms is not None and not 0.5 <= rooms <= _MAX_ROOMS:
            rooms = None
        if size is not None or rooms is not None:
            return size, rooms
    return None, None


def _is_housing_ad(url: str, title: str, text: str, cat_id: str) -> bool:
    blob = f"{title} {text}".lower()
    if looks_like_wanted_ad(title) or any(word in blob for word in _WANTED_MARKERS):
        return False
    if any(word in blob for word in _JUNK):
        return False
    # Kleinanzeigen encode category in the path: /s-anzeige/title/ID-203-LOCATION
    return bool(re.search(rf"-{cat_id}-\d+", url))


def _parse_price(text: str) -> float | None:
    match = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)\s*€", text)
    if not match:
        return None
    return float(match.group(1).replace(".", ""))


def _extract_number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None

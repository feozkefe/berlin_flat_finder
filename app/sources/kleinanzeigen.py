from __future__ import annotations

import logging
import re
import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.districts import detect_district
from app.matching import looks_like_sublet, looks_like_wanted_ad
from app.models import Filters, Listing
from app.sources.base import BROWSER_HEADERS, BaseSource

logger = logging.getLogger(__name__)

BASE = "https://www.kleinanzeigen.de"
# 203 = Wohnung mieten, 199 = WG-Zimmer
CATEGORIES = {
    "apartment": ("wohnungen-mieten", "c203"),
    "wg": ("wg-zimmer", "c199"),
}


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
            slug, code = CATEGORIES[kind]
            taken = 0
            for page in range(1, settings.max_pages_per_source + 1):
                url = self._search_url(slug, code, filters, page)
                try:
                    response = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("Kleinanzeigen search failed url=%s: %s", url, exc)
                    break

                page_listings = self._parse(response.text)
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
        path = f"/s-{slug}/berlin/preis:0:{filters.max_rent}/{code}l3331"
        if page > 1:
            path += f"/seite:{page}"
        return BASE + path

    def _parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        listings: list[Listing] = []
        articles = soup.select("article[data-adid], li[data-adid], article.aditem")
        if not articles:
            # Fallback when markup shifts: split on ad ids.
            for ad_id in dict.fromkeys(re.findall(r'data-adid="(\d+)"', html)):
                listings.append(
                    Listing(
                        id=f"ka_{ad_id}",
                        provider="kleinanzeigen",
                        title=f"Kleinanzeigen {ad_id}",
                        url=f"{BASE}/s-anzeige/{ad_id}",
                        contactable=True,
                    )
                )
            return listings

        for article in articles:
            ad_id = article.get("data-adid")
            if not ad_id:
                continue
            title_el = article.select_one("a.ellipsis, h2 a, a[href*='/s-anzeige/']")
            title = title_el.get_text(" ", strip=True) if title_el else ""
            if not title or looks_like_wanted_ad(title):
                continue
            href = title_el.get("href") if title_el else ""
            url = href if href.startswith("http") else f"{BASE}{href or f'/s-anzeige/{ad_id}'}"
            text = article.get_text(" ", strip=True)
            price = _parse_price(text)
            rooms = _extract_number(text, r"(\d+(?:[.,]\d+)?)\s*(?:Zimmer|Zi\.?)")
            size = _extract_number(text, r"(\d+(?:[.,]\d+)?)\s*m[²2]")
            address_el = article.select_one(".aditem-main--top--left, [class*='location']")
            address = address_el.get_text(" ", strip=True) if address_el else text
            district = detect_district(f"{title} {address}")
            image_el = article.find("img")
            image = None
            if image_el:
                image = image_el.get("src") or image_el.get("data-src")
            listings.append(
                Listing(
                    id=f"ka_{ad_id}",
                    provider="kleinanzeigen",
                    title=title,
                    url=url,
                    price=price,
                    rooms=rooms,
                    size_sqm=size,
                    address=re.sub(r"\s+", " ", address)[:220],
                    district=district.name if district else "",
                    image_url=image if image and image.startswith("http") else None,
                    is_sublet=looks_like_sublet(f"{title} {text}"),
                    contactable=True,
                )
            )
        return listings


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

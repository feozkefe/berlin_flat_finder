from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.districts import detect_district
from app.matching import looks_like_sublet
from app.models import Filters, Listing
from app.sources.base import BROWSER_HEADERS, BaseSource

logger = logging.getLogger(__name__)

BASE = "https://www.wg-gesucht.de"
CITY_ID = 8
API_HEADERS = {**BROWSER_HEADERS, "Accept": "application/json"}

# 0 = WG room, 1 = 1-room flat, 2 = apartment
CATEGORY_SLUGS = {
    "0": "wg-zimmer",
    "1": "1-zimmer-wohnungen",
    "2": "wohnungen",
}


class WgGesuchtSource(BaseSource):
    name = "wg_gesucht"

    async def search(self, client: httpx.AsyncClient, filters: Filters) -> list[Listing]:
        categories = self._categories(filters)
        listings: list[Listing] = []
        seen: set[str] = set()

        for category in categories:
            for page in range(1, settings.max_pages_per_source + 1):
                url = self._search_url(category, page, filters.max_rent)
                try:
                    response = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("WG-Gesucht search failed category=%s page=%s: %s", category, page, exc)
                    break

                offer_ids = self._offer_ids(response.text)
                if not offer_ids:
                    break

                for offer_id in offer_ids:
                    listing_id = f"wg_{offer_id}"
                    if listing_id in seen:
                        continue
                    listing = await self._fetch_offer(client, offer_id, response.text)
                    if listing:
                        listings.append(listing)
                        seen.add(listing.id)
                    if len(listings) >= settings.max_listings_per_source:
                        return listings

        return listings

    def _categories(self, filters: Filters) -> list[str]:
        categories: list[str] = []
        if "wg" in filters.listing_types:
            categories.append("0")
        if "apartment" in filters.listing_types or "sublet" in filters.listing_types:
            categories.extend(["1", "2"])
        return categories or ["0", "1", "2"]

    def _search_url(self, category: str, page: int, max_rent: int) -> str:
        slug = CATEGORY_SLUGS[category]
        return (
            f"{BASE}/{slug}-in-Berlin.{CITY_ID}.{category}.{page}.0.html"
            f"?offer_filter=1&city_id={CITY_ID}&categories%5B%5D={category}"
            f"&rMax={max_rent}&noDeact=1"
        )

    def _offer_ids(self, html: str) -> list[str]:
        ids = re.findall(r'data-id="(\d{5,})"', html)
        # Skip the site's own ad placeholders / duplicates while keeping order.
        return list(dict.fromkeys(ids))

    async def _fetch_offer(self, client: httpx.AsyncClient, offer_id: str, search_html: str) -> Listing | None:
        try:
            response = await client.get(f"{BASE}/api/offers/{offer_id}", headers=API_HEADERS)
            if response.status_code != 200:
                return self._from_html_block(offer_id, search_html)
            return self._from_api(offer_id, response.json(), search_html)
        except httpx.HTTPError:
            return self._from_html_block(offer_id, search_html)

    def _from_api(self, offer_id: str, data: dict, search_html: str) -> Listing | None:
        title = (data.get("offer_title") or "").strip()
        if not title:
            return None

        price = _to_float(data.get("total_costs") or data.get("rent_costs"))
        size = _to_float(data.get("property_size"))
        rooms = _to_float(data.get("number_of_rooms"))
        street = data.get("street") or ""
        postcode = data.get("postcode") or ""
        district_name = data.get("district_custom") or ""
        address = ", ".join(part for part in (street, postcode, district_name) if part)
        available = data.get("available_from_date") or ""
        if available == "00.00.0000":
            available = ""

        category = str(data.get("category", "0"))
        slug = CATEGORY_SLUGS.get(category, "wg-zimmer")
        district_slug = re.sub(r"[^a-zA-Z0-9]+", "-", district_name or "Berlin").strip("-")
        url = f"{BASE}/{slug}-in-{district_slug}.{offer_id}.html"
        blob = f"{title} {address} {data.get('other_information') or ''}"
        district = detect_district(blob)
        image = _image_for_id(search_html, offer_id)

        return Listing(
            id=f"wg_{offer_id}",
            provider="wg_gesucht",
            title=title,
            url=url,
            price=price,
            rooms=rooms if category != "0" else rooms or 1,
            size_sqm=size,
            address=address,
            district=district.name if district else district_name,
            image_url=image,
            available_from=available or None,
            is_sublet=looks_like_sublet(blob) or str(data.get("rent_type", "")) in {"1", "2"},
            contactable=True,
        )

    def _from_html_block(self, offer_id: str, search_html: str) -> Listing | None:
        soup = BeautifulSoup(search_html, "lxml")
        node = soup.find(attrs={"data-id": offer_id})
        if not node:
            return None
        title_el = node.find("h3") or node.find("a")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not title:
            return None
        text = node.get_text(" ", strip=True)
        link = node.find("a", href=True)
        href = link["href"] if link else f"/wg-zimmer-in-Berlin.{offer_id}.html"
        if not href.startswith("http"):
            href = BASE + href
        district = detect_district(text)
        return Listing(
            id=f"wg_{offer_id}",
            provider="wg_gesucht",
            title=title,
            url=href,
            price=_first_euro(text),
            address=text[:180],
            district=district.name if district else "",
            is_sublet=looks_like_sublet(text),
            contactable=True,
        )


def _to_float(value) -> float | None:
    if value in (None, "", "0"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _first_euro(text: str) -> float | None:
    match = re.search(r"(\d[\d.]*)\s*€", text)
    if not match:
        return None
    return _to_float(match.group(1).replace(".", ""))


def _image_for_id(html: str, offer_id: str) -> str | None:
    block = re.search(rf'data-id="{offer_id}"(.*?)data-id="\d{{5,}}"', html, re.DOTALL)
    target = block.group(1) if block else html
    image = re.search(r'(https://img\.wg-gesucht\.de/media/[^"\s]+)', target)
    return image.group(1) if image else None

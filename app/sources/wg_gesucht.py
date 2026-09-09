from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.dates import fill_timing
from app.districts import detect_district, extract_plz
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
# rent_type in both the URL and the API: 0 = any, 1 = befristet (sublet), 2 = unbefristet
RENT_TYPE_ANY = "0"
RENT_TYPE_LIMITED = "1"
RENT_TYPE_UNLIMITED = "2"


class WgGesuchtSource(BaseSource):
    name = "wg_gesucht"

    async def search(self, client: httpx.AsyncClient, filters: Filters) -> list[Listing]:
        categories = self._categories(filters)
        rent_type = self._rent_type(filters)
        listings: list[Listing] = []
        seen: set[str] = set()
        # Without a per-category budget the WG category alone fills the quota and
        # apartments never get fetched.
        budget = max(8, settings.max_listings_per_source // len(categories))

        for category in categories:
            taken = 0
            for page in range(settings.max_pages_per_source):
                url = self._search_url(category, rent_type, page, filters.max_rent)
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
                    seen.add(listing_id)
                    listing = await self._fetch_offer(client, offer_id, response.text, category)
                    if listing:
                        listings.append(listing)
                        taken += 1
                    if len(listings) >= settings.max_listings_per_source:
                        return listings
                    if taken >= budget:
                        break
                if taken >= budget:
                    break

        return listings

    def _categories(self, filters: Filters) -> list[str]:
        categories: list[str] = []
        if "wg" in filters.listing_types:
            categories.append("0")
        if "apartment" in filters.listing_types or "sublet" in filters.listing_types:
            categories.extend(["1", "2"])
        return categories or ["0", "1", "2"]

    def _rent_type(self, filters: Filters) -> str:
        types = set(filters.listing_types)
        if types == {"sublet"}:
            return RENT_TYPE_LIMITED
        if "sublet" not in types:
            return RENT_TYPE_UNLIMITED
        return RENT_TYPE_ANY

    def _search_url(self, category: str, rent_type: str, page: int, max_rent: int) -> str:
        """Path segments are city.category.rent_type.page — page is last, and 0-based."""
        slug = CATEGORY_SLUGS[category]
        return (
            f"{BASE}/{slug}-in-Berlin.{CITY_ID}.{category}.{rent_type}.{page}.html"
            f"?offer_filter=1&city_id={CITY_ID}&categories%5B%5D={category}"
            f"&rMax={max_rent}&noDeact=1"
        )

    def _offer_ids(self, html: str) -> list[str]:
        ids = re.findall(r'data-id="(\d{5,})"', html)
        # Skip the site's own ad placeholders / duplicates while keeping order.
        return list(dict.fromkeys(ids))

    async def _fetch_offer(
        self, client: httpx.AsyncClient, offer_id: str, search_html: str, category: str
    ) -> Listing | None:
        try:
            response = await client.get(f"{BASE}/api/offers/{offer_id}", headers=API_HEADERS)
            if response.status_code != 200:
                return self._from_html_block(offer_id, search_html, category)
            return self._from_api(offer_id, response.json(), search_html, category)
        except httpx.HTTPError:
            return self._from_html_block(offer_id, search_html, category)

    def _from_api(self, offer_id: str, data: dict, search_html: str, wanted_category: str) -> Listing | None:
        title = (data.get("offer_title") or "").strip()
        if not title:
            return None
        if str(data.get("deactivated") or "0") not in {"0", "", "None"}:
            return None

        category = str(data.get("category") or wanted_category)
        if category != wanted_category:
            # The id list on a search page also contains cross-promoted offers.
            return None
        is_room = category == "0"

        price = _to_float(data.get("total_costs")) or _to_float(data.get("rent_costs"))
        size = _to_float(data.get("property_size"))
        street = data.get("street") or ""
        postcode = str(data.get("postcode") or "").strip()
        district_name = data.get("district_custom") or ""
        address = ", ".join(part for part in (street, postcode, district_name) if part)
        available = _clean_date(data.get("available_from_date"))
        available_to = _clean_date(data.get("available_to_date"))

        # A WG ad's number_of_rooms is "0" — it is one room in someone else's flat.
        # Treating that as a 1-room apartment made every min_rooms filter drop it.
        stated_rooms = _to_float(data.get("number_of_rooms"))
        if is_room:
            rooms = None
        elif category == "1":
            # Category 1 is literally "1-Zimmer-Wohnungen"; the field is often blank.
            rooms = stated_rooms or 1.0
        else:
            rooms = stated_rooms
        flat_rooms = None if is_room else rooms
        flatmates = _to_int(data.get("flatshare_inhabitants_total")) if is_room else None

        slug = CATEGORY_SLUGS.get(category, "wg-zimmer")
        district_slug = re.sub(r"[^a-zA-Z0-9]+", "-", district_name or "Berlin").strip("-")
        url = f"{BASE}/{slug}-in-{district_slug}.{offer_id}.html"
        freetext = " ".join(
            str(data.get(key) or "")
            for key in ("freetext_property_description", "freetext_flatshare", "freetext_other")
        )
        blob = f"{title} {address} {freetext}"
        # district_custom is free text the poster typed ("direkt an der U5"), so lead with the PLZ.
        district = detect_district(f"{title} {address}", postcode or extract_plz(address))
        image = _image_for_id(search_html, offer_id)
        limited = str(data.get("rent_type") or "") == RENT_TYPE_LIMITED

        return fill_timing(
            Listing(
                id=f"wg_{offer_id}",
                provider="wg_gesucht",
                title=title,
                url=url,
                price=price,
                rooms=rooms,
                size_sqm=size,
                address=address,
                district=district.name if district else district_name,
                postcode=postcode,
                listing_kind="wg" if is_room else "apartment",
                flat_rooms=flat_rooms,
                flatmates=flatmates,
                image_url=image,
                available_from=available or None,
                available_to=available_to or None,
                is_sublet=limited or bool(available_to) or looks_like_sublet(blob),
                contactable=True,
                private_landlord=is_room,
            ),
            extra_text=blob,
        )

    def _from_html_block(self, offer_id: str, search_html: str, category: str) -> Listing | None:
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
        postcode = extract_plz(text) or ""
        district = detect_district(text, postcode)
        return fill_timing(
            Listing(
                id=f"wg_{offer_id}",
                provider="wg_gesucht",
                title=title,
                url=href,
                price=_first_euro(text),
                address=text[:180],
                district=district.name if district else "",
                postcode=postcode,
                listing_kind="wg" if category == "0" else "apartment",
                is_sublet=looks_like_sublet(text),
                contactable=True,
            ),
            extra_text=text,
        )


def _clean_date(value) -> str:
    raw = str(value or "").strip()
    return "" if raw in {"", "00.00.0000", "0"} else raw


def _to_float(value) -> float | None:
    if value in (None, "", "0"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _to_int(value) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None


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

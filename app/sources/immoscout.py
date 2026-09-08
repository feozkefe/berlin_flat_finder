from __future__ import annotations

import logging
import re

import httpx

from app.config import settings
from app.dates import fill_timing
from app.districts import DISTRICT_BY_ID, detect_district
from app.matching import looks_like_sublet
from app.models import Filters, Listing
from app.sources.base import BaseSource

logger = logging.getLogger(__name__)

MOBILE_API = "https://api.mobile.immobilienscout24.de"
USER_AGENT = "ImmoScout_27.12_26.2_._"
CITY_GEOCODE = "/de/berlin/berlin"


class ImmoScoutSource(BaseSource):
    name = "immoscout"

    async def search(self, client: httpx.AsyncClient, filters: Filters) -> list[Listing]:
        listings: list[Listing] = []
        seen: set[str] = set()
        geocodes = self._geocodes(filters)

        for geocode in geocodes:
            try:
                response = await client.post(
                    f"{MOBILE_API}/search/list",
                    params={
                        "searchType": "region",
                        "realestatetype": "apartmentrent",
                        "geocodes": geocode,
                        "pagenumber": 1,
                        "pagesize": min(settings.max_listings_per_source, 20),
                    },
                    json={"supportedResultListTypes": [], "userData": {}},
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.warning("ImmoScout search failed geocode=%s: %s", geocode, exc)
                continue

            for wrapper in data.get("resultListItems") or []:
                if wrapper.get("type") != "EXPOSE_RESULT":
                    continue
                listing = self._normalize(wrapper.get("item") or {})
                if not listing or listing.id in seen:
                    continue
                listings.append(listing)
                seen.add(listing.id)
                if len(listings) >= settings.max_listings_per_source:
                    return listings

        return listings

    def _geocodes(self, filters: Filters) -> list[str]:
        if 0 < len(filters.districts) <= 3:
            codes = []
            for district_id in filters.districts:
                district = DISTRICT_BY_ID.get(district_id)
                if district and district.immoscout_geocode:
                    codes.append(district.immoscout_geocode)
            if codes:
                return codes
        return [CITY_GEOCODE]

    def _normalize(self, item: dict) -> Listing | None:
        listing_id = str(item.get("id") or "")
        title = (item.get("title") or "").strip()
        if not listing_id or not title:
            return None

        attributes = item.get("attributes") or []
        price = _parse_attr(attributes, 0)
        size = _parse_attr(attributes, 1)
        rooms = _parse_attr(attributes, 2)
        address_obj = item.get("address") or {}
        address = address_obj.get("line") or ""
        picture = item.get("titlePicture") or {}
        image = picture.get("full") or picture.get("preview")
        blob = f"{title} {address}"
        district = detect_district(blob)

        return fill_timing(
            Listing(
                id=f"is24_{listing_id}",
                provider="immoscout",
                title=title,
                url=f"https://www.immobilienscout24.de/expose/{listing_id}",
                price=price,
                rooms=rooms,
                size_sqm=size,
                address=address,
                district=district.name if district else "",
                image_url=image,
                is_sublet=looks_like_sublet(blob),
                contactable=False,
            ),
            extra_text=blob,
        )


def _parse_attr(attributes: list, index: int) -> float | None:
    if index >= len(attributes):
        return None
    raw = str(attributes[index].get("value") or "")
    if "€" in raw:
        digits = re.sub(r"[^\d]", "", raw.split(",")[0])
        try:
            return float(digits) if digits else None
        except ValueError:
            return None
    clean = raw.replace("m²", "").replace("Zi.", "").replace("Zi", "").replace(",", ".").strip()
    match = re.search(r"(\d+(?:\.\d+)?)", clean)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings
from app.dates import fill_timing
from app.districts import DISTRICT_BY_ID, detect_district, extract_plz
from app.matching import contains_excluded, looks_like_sublet
from app.models import Filters, Listing
from app.sources.base import BaseSource

logger = logging.getLogger(__name__)

MOBILE_API = "https://api.mobile.immobilienscout24.de"
USER_AGENT = "ImmoScout_27.12_26.2_._"
CITY_GEOCODE = "/de/berlin/berlin"
MAX_GEOCODES = 6
PAGE_SIZE = 20


class ImmoScoutSource(BaseSource):
    name = "immoscout"

    async def search(self, client: httpx.AsyncClient, filters: Filters) -> list[Listing]:
        listings: list[Listing] = []
        seen: set[str] = set()
        # Same flat posted once per unit in a new build floods the results.
        seen_ads: set[tuple] = set()
        geocodes = self._geocodes(filters)
        budget = max(8, settings.max_listings_per_source // len(geocodes))

        for geocode in geocodes:
            taken = 0
            for page in range(1, settings.max_pages_per_source + 1):
                data = await self._fetch_page(client, geocode, page, filters)
                if data is None:
                    break

                items = [
                    wrapper.get("item") or {}
                    for wrapper in (data.get("resultListItems") or [])
                    if wrapper.get("type") == "EXPOSE_RESULT"
                ]
                if not items:
                    break

                for item in items:
                    listing = self._normalize(item)
                    if not listing or listing.id in seen:
                        continue
                    # Swap ads (Tauschwohnung) outnumber real rentals here and would
                    # otherwise use up the whole page budget before the scanner
                    # ever gets to drop them.
                    if contains_excluded(f"{listing.title} {listing.address}", filters.exclude_keywords):
                        continue
                    fingerprint = (listing.title, listing.address, listing.price, listing.size_sqm)
                    if fingerprint in seen_ads:
                        continue
                    seen.add(listing.id)
                    seen_ads.add(fingerprint)
                    listings.append(listing)
                    taken += 1
                    if len(listings) >= settings.max_listings_per_source:
                        return listings
                    if taken >= budget:
                        break

                if taken >= budget or page >= (data.get("numberOfPages") or 1):
                    break

        return listings

    async def _fetch_page(
        self, client: httpx.AsyncClient, geocode: str, page: int, filters: Filters
    ) -> dict | None:
        try:
            response = await client.post(
                f"{MOBILE_API}/search/list",
                params={
                    "searchType": "region",
                    "realestatetype": "apartmentrent",
                    "geocodes": geocode,
                    "pagenumber": page,
                    "pagesize": PAGE_SIZE,
                    "price": f"-{filters.max_rent}",
                    "numberofrooms": f"{filters.min_rooms:g}-",
                },
                json={"supportedResultListTypes": [], "userData": {}},
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("ImmoScout search failed geocode=%s page=%s: %s", geocode, page, exc)
            return None

    def _geocodes(self, filters: Filters) -> list[str]:
        """Narrow to the chosen districts when every one of them has a usable geocode."""
        if not (0 < len(filters.districts) <= MAX_GEOCODES):
            return [CITY_GEOCODE]

        codes = []
        for district_id in filters.districts:
            district = DISTRICT_BY_ID.get(district_id)
            if not district or not district.immoscout_geocode:
                # No region geocode for this district (the API 412s on some of
                # them). Search all of Berlin and let the district filter narrow.
                return [CITY_GEOCODE]
            codes.append(district.immoscout_geocode)
        return codes or [CITY_GEOCODE]

    def _normalize(self, item: dict) -> Listing | None:
        listing_id = str(item.get("id") or "")
        title = (item.get("title") or "").strip()
        if not listing_id or not title:
            return None

        price, size, rooms = _parse_attributes(item.get("attributes") or [])
        address_obj = item.get("address") or {}
        address = address_obj.get("line") or ""
        postcode = extract_plz(address) or ""
        picture = item.get("titlePicture") or {}
        image = picture.get("full") or picture.get("preview")
        blob = f"{title} {address}"
        district = detect_district(blob, postcode)

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
                postcode=postcode,
                listing_kind="apartment",
                image_url=image,
                is_sublet=looks_like_sublet(blob),
                # Messaging needs an ImmoScout account, so these rank below the rest.
                contactable=False,
                private_landlord=bool(item.get("isPrivate")),
            ),
            extra_text=blob,
        )


def _parse_attributes(attributes: list) -> tuple[float | None, float | None, float | None]:
    """Attributes arrive as unlabelled values. Read the unit, not the position."""
    price = size = rooms = None
    for attribute in attributes:
        raw = str(attribute.get("value") or "")
        clean = raw.replace(" ", " ").replace(" ", " ").strip()
        if not clean:
            continue
        if "€" in clean:
            price = price if price is not None else _to_float(clean.split(",")[0], thousands=True)
        elif "m²" in clean or "m2" in clean:
            size = size if size is not None else _to_float(clean.replace("m²", "").replace("m2", ""))
        elif "zi" in clean.lower():
            rooms = rooms if rooms is not None else _to_float(re.sub(r"(?i)zi\.?", "", clean))
    return price, size, rooms


def _to_float(raw: str, *, thousands: bool = False) -> float | None:
    text = raw.replace(".", "") if thousands else raw.replace(".", ",")
    match = re.search(r"(\d+(?:,\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None

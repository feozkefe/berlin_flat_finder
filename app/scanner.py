from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app import db
from app.config import settings
from app.districts import matches_selected
from app.matching import attach_cross_matches, contains_excluded, looks_like_wanted_ad
from app.models import Filters, Listing, ScanResult
from app.sources import SOURCE_MAP

logger = logging.getLogger(__name__)


def listing_passes(listing: Listing, filters: Filters) -> bool:
    blob = f"{listing.title} {listing.address} {listing.district}"
    if looks_like_wanted_ad(listing.title):
        return False
    if contains_excluded(blob, filters.exclude_keywords):
        return False
    if not matches_selected(blob, filters.districts):
        return False
    if listing.price is not None and listing.price > filters.max_rent:
        return False
    if listing.rooms is not None and listing.rooms + 0.01 < filters.min_rooms:
        return False
    if listing.size_sqm is not None and filters.min_sqm and listing.size_sqm < filters.min_sqm:
        return False

    types = set(filters.listing_types)
    if types == {"sublet"}:
        return listing.is_sublet
    if types == {"wg"} and listing.provider == "immoscout":
        return False
    if "sublet" not in types and listing.is_sublet:
        return False
    return True


async def run_scan() -> ScanResult:
    filters = db.load_filters()
    started = datetime.now(timezone.utc)
    errors: list[str] = []
    found: list[Listing] = []

    async with httpx.AsyncClient(timeout=settings.request_timeout, follow_redirects=True) as client:
        for source_name in filters.sources:
            source_cls = SOURCE_MAP.get(source_name)
            if not source_cls:
                continue
            try:
                batch = await source_cls().search(client, filters)
                found.extend(batch)
                logger.info("%s returned %d listings", source_name, len(batch))
            except Exception as exc:
                message = f"{source_name}: {exc}"
                errors.append(message)
                logger.exception("Source failed: %s", source_name)
            await asyncio.sleep(1.2)

    found = attach_cross_matches(found)
    kept = [listing for listing in found if listing_passes(listing, filters)]

    already = db.known_ids()
    first_scan = not already
    new_listings = [listing for listing in kept if listing.id not in already]

    # First scan is a silent baseline so Telegram is not flooded with old ads.
    db.upsert_listings(kept, mark_notified=first_scan)

    finished = datetime.now(timezone.utc)
    result = ScanResult(
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        new_listings=[] if first_scan else new_listings,
        total_found=len(kept),
        errors=errors,
        first_scan=first_scan,
    )
    db.save_scan(
        result.started_at,
        result.finished_at,
        len(result.new_listings),
        result.total_found,
        result.errors,
        result.first_scan,
    )
    logger.info(
        "Scan done first=%s found=%s new=%s errors=%s",
        first_scan,
        result.total_found,
        len(result.new_listings),
        errors,
    )
    return result

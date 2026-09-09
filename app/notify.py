from __future__ import annotations

import logging

from telegram import Bot

from app.config import settings
from app.models import Listing, ScanResult
from app.scanner import rank

BATCH = 8

logger = logging.getLogger(__name__)

PROVIDER_LABEL = {
    "wg_gesucht": "WG-Gesucht",
    "kleinanzeigen": "Kleinanzeigen",
    "immoscout": "ImmoScout24",
}


def writable_urls(listing: Listing) -> list[dict[str, str]]:
    """Places you can message about this ad, other than the ad's own site."""
    return [alt for alt in listing.alt_urls if alt.get("provider") != listing.provider]


def can_message(listing: Listing) -> bool:
    return listing.contactable or bool(writable_urls(listing))


def _meta(listing: Listing) -> str:
    if listing.listing_kind == "wg":
        rooms = f"room in {listing.flatmates + 1}-person WG" if listing.flatmates else "WG room"
    else:
        rooms = f"{listing.rooms:g} Zi" if listing.rooms else None
    bits = [
        listing.district or "Berlin",
        rooms,
        f"{listing.size_sqm:g} m²" if listing.size_sqm else None,
        f"{listing.price:,.0f} €".replace(",", ".") if listing.price else None,
    ]
    return " · ".join(bit for bit in bits if bit)


def _timing(listing: Listing) -> str | None:
    bits = []
    if listing.available_from:
        bits.append(f"from {listing.available_from}")
    if listing.available_to:
        bits.append(f"until {listing.available_to}")
    elif listing.duration_months:
        bits.append(f"{listing.duration_months} months")
    return " · ".join(bits) if bits else None


def format_listing(listing: Listing) -> str:
    lines = [
        f"🏠 {PROVIDER_LABEL.get(listing.provider, listing.provider)}",
        listing.title,
        _meta(listing),
    ]
    if listing.address:
        lines.append(f"📍 {listing.address}")
    timing = _timing(listing)
    if timing:
        lines.append(f"📅 {timing}")
    if listing.is_sublet:
        lines.append("⏳ Zwischenmiete / sublet")

    alts = writable_urls(listing)
    if listing.contactable:
        lines.append("✉️ You can write here" + (" · private landlord" if listing.private_landlord else ""))
    elif alts:
        lines.append("✉️ No messaging here — same ad where you can write:")
        for alt in alts:
            lines.append(f"   {PROVIDER_LABEL.get(alt['provider'], alt['provider'])}: {alt['url']}")
    else:
        lines.append("👀 View only — no direct message, no copy found elsewhere.")

    lines.append(listing.url)
    return "\n".join(line for line in lines if line)


def format_listing_compact(listing: Listing, index: int) -> str:
    label = PROVIDER_LABEL.get(listing.provider, listing.provider)
    bits = [
        f"{listing.price:,.0f}€".replace(",", ".") if listing.price else None,
        listing.district or None,
        "WG room" if listing.listing_kind == "wg" else (f"{listing.rooms:g} Zi" if listing.rooms else None),
        f"{listing.size_sqm:g} m²" if listing.size_sqm else None,
        _timing(listing),
    ]
    meta = " · ".join(bit for bit in bits if bit)
    head = f"{index}. {'✉️' if can_message(listing) else '👀'} {label} · {meta}"
    extra = ""
    if not listing.contactable:
        alts = writable_urls(listing)
        extra = "\n" + "\n".join(alt["url"] for alt in alts) if alts else "\n(view only)"
    return f"{head}\n{listing.title}\n{listing.url}{extra}"


async def send_listing_batches(bot: Bot, chat_id: str, listings: list[Listing]) -> None:
    """Writable ads first, in their own block, so they are not buried."""
    if not listings:
        return
    ordered = rank(listings)
    groups = [
        ("✉️ You can message these", [item for item in ordered if can_message(item)]),
        ("👀 View only", [item for item in ordered if not can_message(item)]),
    ]

    index = 0
    for heading, group in groups:
        if not group:
            continue
        await bot.send_message(chat_id=chat_id, text=f"{heading} ({len(group)})")
        for start in range(0, len(group), BATCH):
            chunk = group[start : start + BATCH]
            lines = []
            for item in chunk:
                index += 1
                lines.append(format_listing_compact(item, index))
            await bot.send_message(
                chat_id=chat_id,
                text="\n\n".join(lines),
                disable_web_page_preview=True,
            )


def format_scan_summary(result: ScanResult) -> str:
    extra = f"\nErrors: {', '.join(result.errors)}" if result.errors else ""
    writable = sum(1 for item in result.new_listings if can_message(item))
    if result.first_scan:
        return (
            f"First scan: {result.total_found} matching listings, {writable} you can message.\n"
            "Later scans only send new ones."
            f"{extra}"
        )
    if not result.new_listings:
        return f"Scan done, nothing new. Matches: {result.total_found}.{extra}"
    return f"{len(result.new_listings)} new listings, {writable} you can message:{extra}"


async def send_scan_result(chat_id: str, result: ScanResult) -> None:
    if not settings.telegram_bot_token or not chat_id:
        return
    bot = Bot(settings.telegram_bot_token)
    try:
        await bot.send_message(chat_id=chat_id, text=format_scan_summary(result))
        await send_listing_batches(bot, chat_id, result.new_listings)
    except Exception:
        logger.exception("Telegram send failed")

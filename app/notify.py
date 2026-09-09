from __future__ import annotations

import logging

from telegram import Bot

from app.config import settings
from app.models import Listing, ScanResult

BATCH = 8

logger = logging.getLogger(__name__)

PROVIDER_LABEL = {
    "wg_gesucht": "WG-Gesucht",
    "kleinanzeigen": "Kleinanzeigen",
    "immoscout": "ImmoScout24",
}


def format_listing(listing: Listing) -> str:
    bits = [
        listing.district or "Berlin",
        f"{listing.rooms:g} Zi" if listing.rooms else None,
        f"{listing.size_sqm:g} m²" if listing.size_sqm else None,
        f"{listing.price:,.0f} €".replace(",", ".") if listing.price else None,
    ]
    meta = " · ".join(bit for bit in bits if bit)
    lines = [
        f"🏠 {PROVIDER_LABEL.get(listing.provider, listing.provider)}",
        listing.title,
        meta,
    ]
    if listing.address:
        lines.append(f"📍 {listing.address}")
    if listing.available_from:
        lines.append(f"📅 {listing.available_from}")
    if listing.is_sublet:
        lines.append("⏳ Zwischenmiete / sublet")

    if listing.provider == "immoscout":
        writable = [alt for alt in listing.alt_urls if alt.get("provider") != "immoscout"]
        if writable:
            lines.append("✉️ Can't message on ImmoScout — same ad elsewhere:")
            for alt in writable:
                label = PROVIDER_LABEL.get(alt["provider"], alt["provider"])
                lines.append(f"   {label}: {alt['url']}")
        else:
            lines.append("⚠️ ImmoScout: no direct message, no copy found on other sites.")
    else:
        lines.append("✉️ You can write here")

    lines.append(listing.url)
    return "\n".join(lines)


def format_listing_compact(listing: Listing, index: int) -> str:
    label = PROVIDER_LABEL.get(listing.provider, listing.provider)
    bits = [
        f"{listing.price:,.0f}€".replace(",", ".") if listing.price else None,
        listing.district or None,
        f"{listing.rooms:g} Zi" if listing.rooms else None,
        f"ab {listing.available_from}" if listing.available_from else None,
        f"{listing.duration_months} mo" if listing.duration_months else None,
    ]
    meta = " · ".join(bit for bit in bits if bit)
    extra = ""
    if listing.provider == "immoscout":
        writable = [alt for alt in listing.alt_urls if alt.get("provider") != "immoscout"]
        extra = "\n" + "\n".join(alt["url"] for alt in writable) if writable else " (can't message)"
    return f"{index}. {label} · {meta}\n{listing.title}\n{listing.url}{extra}"


async def send_listing_batches(bot: Bot, chat_id: str, listings: list[Listing]) -> None:
    if not listings:
        return
    for start in range(0, len(listings), BATCH):
        chunk = listings[start : start + BATCH]
        lines = [format_listing_compact(item, start + i + 1) for i, item in enumerate(chunk)]
        await bot.send_message(chat_id=chat_id, text="\n\n".join(lines), disable_web_page_preview=True)


def format_scan_summary(result: ScanResult) -> str:
    extra = f"\nErrors: {', '.join(result.errors)}" if result.errors else ""
    if result.first_scan:
        return (
            f"First scan: {result.total_found} matching listings. Links below.\n"
            "Later scans only send new ones."
            f"{extra}"
        )
    if not result.new_listings:
        return f"Scan done, nothing new. Matches: {result.total_found}.{extra}"
    return f"{len(result.new_listings)} new listings:"


async def send_scan_result(chat_id: str, result: ScanResult) -> None:
    if not settings.telegram_bot_token or not chat_id:
        return
    bot = Bot(settings.telegram_bot_token)
    try:
        await bot.send_message(chat_id=chat_id, text=format_scan_summary(result))
        await send_listing_batches(bot, chat_id, result.new_listings)
    except Exception:
        logger.exception("Telegram send failed")

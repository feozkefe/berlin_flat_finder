from __future__ import annotations

import logging

from telegram import Bot

from app.config import settings
from app.models import Listing, ScanResult

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
            lines.append("✉️ ImmoScout'tan yazılamıyor — aynı ilan başka yerde:")
            for alt in writable:
                label = PROVIDER_LABEL.get(alt["provider"], alt["provider"])
                lines.append(f"   {label}: {alt['url']}")
        else:
            lines.append("⚠️ ImmoScout: ev sahibine doğrudan yazılamıyor, başka sitede kopyası yok.")
    else:
        lines.append("✉️ Buradan yazılabilir")

    lines.append(listing.url)
    return "\n".join(lines)


def format_scan_summary(result: ScanResult) -> str:
    extra = f"\nHatalar: {', '.join(result.errors)}" if result.errors else ""
    if result.first_scan:
        return (
            f"İlk tarama: {result.total_found} eşleşen ilan. Linkler aşağıda.\n"
            "Sonraki taramalarda sadece yeniler gelir."
            f"{extra}"
        )
    if not result.new_listings:
        return f"Tarama bitti, yeni ilan yok. Toplam eşleşen: {result.total_found}.{extra}"
    return f"{len(result.new_listings)} yeni ilan:"


async def send_scan_result(chat_id: str, result: ScanResult) -> None:
    if not settings.telegram_bot_token or not chat_id:
        return
    bot = Bot(settings.telegram_bot_token)
    try:
        await bot.send_message(chat_id=chat_id, text=format_scan_summary(result))
        for listing in result.new_listings[: settings.max_telegram_per_scan]:
            await bot.send_message(chat_id=chat_id, text=format_listing(listing), disable_web_page_preview=False)
        leftover = len(result.new_listings) - settings.max_telegram_per_scan
        if leftover > 0:
            await bot.send_message(
                chat_id=chat_id,
                text=f"+{leftover} ilan daha. Hepsini görmek için /latest veya Railway web URL.",
            )
    except Exception:
        logger.exception("Telegram send failed")

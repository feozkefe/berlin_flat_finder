from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app import db
from app.config import settings
from app.districts import DISTRICTS
from app.models import Filters, Listing
from app.notify import format_listing, send_scan_result
from app.scanner import run_scan

logger = logging.getLogger(__name__)

DISTRICT_PICK, RENT_PICK, ROOMS_PICK, TYPE_PICK, INTERVAL_PICK = range(5)


def _district_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for district in DISTRICTS:
        mark = "✓ " if district.id in selected else ""
        row.append(InlineKeyboardButton(f"{mark}{district.name}", callback_data=f"d:{district.id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Hepsi / fark etmez", callback_data="d:all")])
    rows.append([InlineKeyboardButton("Devam →", callback_data="d:done")])
    return InlineKeyboardMarkup(rows)


def _type_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    labels = {"wg": "WG odası", "apartment": "Daire", "sublet": "Zwischenmiete / sublet"}
    buttons = [
        InlineKeyboardButton(
            f"{'✓ ' if key in selected else ''}{label}",
            callback_data=f"t:{key}",
        )
        for key, label in labels.items()
    ]
    return InlineKeyboardMarkup([buttons[:2], buttons[2:], [InlineKeyboardButton("Devam →", callback_data="t:done")]])


def _interval_keyboard(current: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(("✓ " if current == 12 else "") + "12 saat", callback_data="i:12"),
                InlineKeyboardButton(("✓ " if current == 24 else "") + "24 saat", callback_data="i:24"),
            ]
        ]
    )


def _bind_chat(filters: Filters, chat_id: int | str) -> Filters:
    filters.telegram_chat_id = str(chat_id)
    return db.save_filters(filters)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = _bind_chat(db.load_filters(), update.effective_chat.id)
    await update.message.reply_text(
        "Berlin Flat Finder.\n\n"
        "Filtreleri buradan kur: /setup\n"
        "Durum: /status\n"
        "Hemen tara: /scan\n"
        "Durdur / aç: /pause /resume\n\n"
        f"Chat bağlandı. Şu an {filters.interval_hours} saatte bir tarama."
    )


async def _goto_rent(query) -> int:
    await query.edit_message_text("Max warm kira? Sadece sayı yaz, örn. 1100")
    return RENT_PICK


async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    filters = db.load_filters()
    context.user_data["filters"] = filters.to_dict()
    old_id = context.user_data.pop("district_msg_id", None)
    if old_id and update.effective_chat:
        try:
            await context.bot.delete_message(update.effective_chat.id, old_id)
        except Exception:
            pass
    msg = await update.message.reply_text(
        "Mahalleleri işaretle, bitince bir kez Devam.\n"
        "Tüm Berlin için Hepsi — o zaman direkt kiraya geçer.",
        reply_markup=_district_keyboard(filters.districts),
    )
    context.user_data["district_msg_id"] = msg.message_id
    return DISTRICT_PICK


async def district_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.setdefault("filters", Filters().to_dict())
    selected: list[str] = list(data.get("districts") or [])
    action = query.data.split(":", 1)[1]
    if action == "all":
        data["districts"] = []
        return await _goto_rent(query)
    if action == "done":
        data["districts"] = selected
        return await _goto_rent(query)
    if action in selected:
        selected.remove(action)
    else:
        selected.append(action)
    data["districts"] = selected
    await query.edit_message_reply_markup(reply_markup=_district_keyboard(selected))
    return DISTRICT_PICK


async def rent_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").replace("€", "").replace(".", "").strip()
    try:
        rent = int(text)
        if rent < 200 or rent > 8000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("200-8000 arası bir sayı yaz, örn. 1100")
        return RENT_PICK
    context.user_data["filters"]["max_rent"] = rent
    await update.message.reply_text("Minimum oda? 1 / 1.5 / 2 ...")
    return ROOMS_PICK


async def rooms_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        rooms = float((update.message.text or "").replace(",", "."))
        if rooms < 1 or rooms > 8:
            raise ValueError
    except ValueError:
        await update.message.reply_text("1 ile 8 arası bir sayı yaz.")
        return ROOMS_PICK
    context.user_data["filters"]["min_rooms"] = rooms
    types = context.user_data["filters"].get("listing_types") or ["wg", "apartment", "sublet"]
    await update.message.reply_text(
        "Ne arıyorsun? İstediğini işaretle, sonra Devam.",
        reply_markup=_type_keyboard(types),
    )
    return TYPE_PICK


async def type_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected = list(context.user_data["filters"].get("listing_types") or [])
    action = query.data.split(":", 1)[1]
    if action == "done":
        if not selected:
            selected = ["wg", "apartment", "sublet"]
        context.user_data["filters"]["listing_types"] = selected
        interval = int(context.user_data["filters"].get("interval_hours") or 12)
        await query.edit_message_text(
            "Kaç saatte bir tarayayım?",
            reply_markup=_interval_keyboard(interval),
        )
        return INTERVAL_PICK
    if action in selected:
        selected.remove(action)
    else:
        selected.append(action)
    context.user_data["filters"]["listing_types"] = selected
    await query.edit_message_reply_markup(reply_markup=_type_keyboard(selected))
    return TYPE_PICK


async def interval_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    hours = int(query.data.split(":", 1)[1])
    payload = context.user_data["filters"]
    payload["interval_hours"] = hours
    payload["telegram_chat_id"] = str(update.effective_chat.id)
    payload["enabled"] = True
    filters = db.save_filters(Filters.from_dict(payload))
    names = ", ".join(
        next((d.name for d in DISTRICTS if d.id == item), item) for item in filters.districts
    ) or "tüm Berlin"
    await query.edit_message_text(
        "Kaydedildi.\n"
        f"Mahalle: {names}\n"
        f"Max kira: {filters.max_rent} €\n"
        f"Min oda: {filters.min_rooms:g}\n"
        f"Tipler: {', '.join(filters.listing_types)}\n"
        f"Aralık: {filters.interval_hours} saat\n\n"
        "Hemen denemek için /scan"
    )
    scheduler = context.application.bot_data.get("reschedule")
    if scheduler:
        scheduler()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("İptal.")
    return ConversationHandler.END


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = _bind_chat(db.load_filters(), update.effective_chat.id)
    scan = db.latest_scan()
    names = ", ".join(
        next((d.name for d in DISTRICTS if d.id == item), item) for item in filters.districts
    ) or "tüm Berlin"
    last = "henüz yok"
    if scan:
        last = f"{scan['finished_at']} — {scan['new_count']} yeni / {scan['total_count']} eşleşen"
    await update.message.reply_text(
        f"{'Açık' if filters.enabled else 'Duraklatıldı'}\n"
        f"Mahalle: {names}\n"
        f"Max kira: {filters.max_rent} € · min {filters.min_rooms:g} oda · {filters.min_sqm} m²\n"
        f"Tip: {', '.join(filters.listing_types)}\n"
        f"Kaynak: {', '.join(filters.sources)}\n"
        f"Aralık: {filters.interval_hours} saat\n"
        f"Son tarama: {last}"
    )


async def scan_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = _bind_chat(db.load_filters(), update.effective_chat.id)
    await update.message.reply_text("Tarıyorum, 20-40 sn sürebilir...")
    result = await run_scan()
    await send_scan_result(filters.telegram_chat_id, result)
    if result.new_listings:
        return
    if not result.first_scan:
        await update.message.reply_text("Yeni ilan çıkmadı.")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = db.load_filters()
    filters.enabled = False
    _bind_chat(filters, update.effective_chat.id)
    await update.message.reply_text("Taramalar durdu. /resume ile aç.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = db.load_filters()
    filters.enabled = True
    _bind_chat(filters, update.effective_chat.id)
    await update.message.reply_text("Taramalar açık.")


async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.recent_listings(5)
    if not rows:
        await update.message.reply_text("Henüz kayıtlı ilan yok. /scan")
        return
    for row in rows:
        await update.message.reply_text(format_listing(Listing.from_dict(row)))


def build_application() -> Application | None:
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN boş — bot kapalı, sadece web çalışır.")
        return None

    application = Application.builder().token(settings.telegram_bot_token).build()
    setup_handler = ConversationHandler(
        entry_points=[CommandHandler("setup", setup)],
        states={
            DISTRICT_PICK: [CallbackQueryHandler(district_pick, pattern=r"^d:")],
            RENT_PICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, rent_pick)],
            ROOMS_PICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, rooms_pick)],
            TYPE_PICK: [CallbackQueryHandler(type_pick, pattern=r"^t:")],
            INTERVAL_PICK: [CallbackQueryHandler(interval_pick, pattern=r"^i:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_chat=True,
        per_user=True,
        per_message=False,
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(setup_handler)
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("scan", scan_now))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("latest", latest))
    return application

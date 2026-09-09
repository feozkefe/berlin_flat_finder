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
from app.dates import parse_user_months, parse_user_start
from app.districts import DISTRICTS
from app.models import Filters, Listing
from app.notify import send_listing_batches, send_scan_result
from app.scanner import run_scan

logger = logging.getLogger(__name__)

DISTRICT_PICK, RENT_PICK, ROOMS_PICK, DATE_PICK, MONTHS_PICK, TYPE_PICK, INTERVAL_PICK = range(7)


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
    rows.append([InlineKeyboardButton("All Berlin / no preference", callback_data="d:all")])
    rows.append([InlineKeyboardButton("Continue →", callback_data="d:done")])
    return InlineKeyboardMarkup(rows)


def _type_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    labels = {"wg": "WG room", "apartment": "Apartment", "sublet": "Sublet / Zwischenmiete"}
    buttons = [
        InlineKeyboardButton(
            f"{'✓ ' if key in selected else ''}{label}",
            callback_data=f"t:{key}",
        )
        for key, label in labels.items()
    ]
    return InlineKeyboardMarkup([buttons[:2], buttons[2:], [InlineKeyboardButton("Continue →", callback_data="t:done")]])


def _interval_keyboard(current: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(("✓ " if current == 12 else "") + "12 hours", callback_data="i:12"),
                InlineKeyboardButton(("✓ " if current == 24 else "") + "24 hours", callback_data="i:24"),
            ]
        ]
    )


def _months_label(filters: Filters) -> str:
    if filters.min_months and filters.max_months:
        return f"{filters.min_months}-{filters.max_months} months"
    if filters.min_months:
        return f"min {filters.min_months} month" + ("s" if filters.min_months != 1 else "")
    return f"max {filters.max_months} months"


def _bind_chat(filters: Filters, chat_id: int | str) -> Filters:
    filters.telegram_chat_id = str(chat_id)
    return db.save_filters(filters)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = _bind_chat(db.load_filters(), update.effective_chat.id)
    await update.message.reply_text(
        "Berlin Flat Finder.\n\n"
        "Set filters: /setup\n"
        "Status: /status\n"
        "Scan now: /scan\n"
        "Pause / resume: /pause /resume\n"
        "Clear saved listings: /reset\n\n"
        f"Chat linked. Scanning every {filters.interval_hours} hours."
    )


async def _goto_rent(query) -> int:
    await query.edit_message_text("Max warm rent? Number only, e.g. 1100")
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
        "Tap districts, then Continue once.\n"
        "All Berlin → skip districts and go to rent.",
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
        await update.message.reply_text("Enter a number between 200 and 8000, e.g. 1100")
        return RENT_PICK
    context.user_data["filters"]["max_rent"] = rent
    await update.message.reply_text(
        "Minimum rooms? 1 / 1.5 / 2 ...\n"
        "Only applies to whole apartments — WG rooms are always one room."
    )
    return ROOMS_PICK


async def rooms_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        rooms = float((update.message.text or "").replace(",", "."))
        if rooms < 1 or rooms > 8:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Enter a number between 1 and 8.")
        return ROOMS_PICK
    context.user_data["filters"]["min_rooms"] = rooms
    await update.message.reply_text(
        "Available from? e.g. 01.10.2026\n"
        "0 = anytime / immediately"
    )
    return DATE_PICK


async def date_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parsed = parse_user_start(update.message.text or "")
    if parsed == "invalid":
        await update.message.reply_text("Use 01.10.2026 or 0.")
        return DATE_PICK
    context.user_data["filters"]["start_from"] = parsed
    await update.message.reply_text(
        "How many months? Minimum 1.\n"
        "e.g. 1  |  6  |  6-12"
    )
    return MONTHS_PICK


async def months_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parsed = parse_user_months(update.message.text or "")
    if parsed is None:
        await update.message.reply_text("Write 1 or 6-12.")
        return MONTHS_PICK
    context.user_data["filters"]["min_months"] = parsed[0]
    context.user_data["filters"]["max_months"] = parsed[1]
    types = context.user_data["filters"].get("listing_types") or ["wg", "apartment", "sublet"]
    await update.message.reply_text(
        "What are you looking for? Toggle, then Continue.",
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
            "How often should I scan?",
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
    ) or "all Berlin"
    await query.edit_message_text(
        "Saved.\n"
        f"Districts: {names}\n"
        f"Max rent: {filters.max_rent} €\n"
        f"Min rooms: {filters.min_rooms:g}\n"
        f"Available from: {filters.start_from or 'anytime'}\n"
        f"Duration: {_months_label(filters)}\n"
        f"Types: {', '.join(filters.listing_types)}\n"
        f"Scan every: {filters.interval_hours} hours\n\n"
        "Try /scan now"
    )
    scheduler = context.application.bot_data.get("reschedule")
    if scheduler:
        scheduler()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = _bind_chat(db.load_filters(), update.effective_chat.id)
    scan = db.latest_scan()
    names = ", ".join(
        next((d.name for d in DISTRICTS if d.id == item), item) for item in filters.districts
    ) or "all Berlin"
    last = "none yet"
    if scan:
        last = f"{scan['finished_at']} — {scan['new_count']} new / {scan['total_count']} matches"
    await update.message.reply_text(
        f"{'On' if filters.enabled else 'Paused'}\n"
        f"Districts: {names}\n"
        f"Max rent: {filters.max_rent} € · min {filters.min_rooms:g} rooms · {filters.min_sqm} m²\n"
        f"Available from: {filters.start_from or 'anytime'} · duration: {_months_label(filters)}\n"
        f"Types: {', '.join(filters.listing_types)}\n"
        f"Sources: {', '.join(filters.sources)}\n"
        f"Every {filters.interval_hours} hours\n"
        f"Last scan: {last}"
    )


async def scan_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = _bind_chat(db.load_filters(), update.effective_chat.id)
    await update.message.reply_text("Scanning, can take 20-40 seconds...")
    result = await run_scan()
    await send_scan_result(filters.telegram_chat_id, result)
    if result.new_listings:
        return
    if not result.first_scan:
        await update.message.reply_text("No new listings.")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = db.load_filters()
    filters.enabled = False
    _bind_chat(filters, update.effective_chat.id)
    await update.message.reply_text("Scans paused. /resume to turn them back on.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = db.load_filters()
    filters.enabled = True
    _bind_chat(filters, update.effective_chat.id)
    await update.message.reply_text("Scans are on.")


async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.recent_listings(200)
    if not rows:
        await update.message.reply_text("No saved listings yet. /scan")
        return
    await update.message.reply_text(f"{len(rows)} saved listings:")
    listings = [Listing.from_dict(row) for row in rows]
    await send_listing_batches(context.bot, str(update.effective_chat.id), listings)


async def reset_listings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    count = db.clear_listings()
    await update.message.reply_text(
        f"Cleared {count} saved listings. Filters kept.\n"
        "Run /scan to fetch them again with links."
    )


def build_application() -> Application | None:
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN empty — bot off, web only.")
        return None

    application = Application.builder().token(settings.telegram_bot_token).build()
    setup_handler = ConversationHandler(
        entry_points=[CommandHandler("setup", setup)],
        states={
            DISTRICT_PICK: [CallbackQueryHandler(district_pick, pattern=r"^d:")],
            RENT_PICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, rent_pick)],
            ROOMS_PICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, rooms_pick)],
            DATE_PICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, date_pick)],
            MONTHS_PICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, months_pick)],
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
    application.add_handler(CommandHandler("reset", reset_listings))
    return application

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.bot import build_application
from app.config import settings
from app.districts import public_districts
from app.models import Filters
from app.notify import send_scan_result
from app.scanner import run_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
scheduler = AsyncIOScheduler()
telegram_app = None


async def scheduled_job() -> None:
    filters = db.load_filters()
    if not filters.enabled:
        logger.info("Scan skipped — paused")
        return
    result = await run_scan()
    await send_scan_result(filters.telegram_chat_id, result)


def reschedule() -> None:
    filters = db.load_filters()
    hours = filters.interval_hours if filters.interval_hours in (12, 24) else 12
    if scheduler.get_job("flat-scan"):
        scheduler.remove_job("flat-scan")
    scheduler.add_job(scheduled_job, "interval", hours=hours, id="flat-scan", replace_existing=True)
    logger.info("Scheduler set to every %s hours", hours)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    db.init_db()
    reschedule()
    scheduler.start()

    telegram_app = build_application()
    if telegram_app:
        telegram_app.bot_data["reschedule"] = reschedule
        await telegram_app.initialize()
        await telegram_app.start()
        if telegram_app.updater:
            await telegram_app.updater.start_polling()
        logger.info("Telegram bot polling")

    if settings.scan_on_start:
        asyncio.create_task(scheduled_job())

    yield

    scheduler.shutdown(wait=False)
    if telegram_app:
        if telegram_app.updater:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


api = FastAPI(title="Berlin Flat Finder", lifespan=lifespan)
api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@api.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@api.get("/api/meta")
async def meta() -> dict:
    return {
        "districts": public_districts(),
        "bot_configured": bool(settings.telegram_bot_token),
    }


@api.get("/api/settings")
async def get_settings() -> dict:
    return db.load_filters().to_dict()


@api.post("/api/settings")
async def post_settings(payload: dict) -> dict:
    filters = Filters.from_dict(payload)
    db.save_filters(filters)
    reschedule()
    return filters.to_dict()


@api.get("/api/listings")
async def listings() -> dict:
    return {"listings": db.recent_listings(), "scan": db.latest_scan()}


@api.post("/api/scan")
async def scan_endpoint() -> dict:
    filters = db.load_filters()
    if not filters.enabled:
        raise HTTPException(status_code=409, detail="Taramalar duraklatıldı.")
    result = await run_scan()
    await send_scan_result(filters.telegram_chat_id, result)
    return {
        "first_scan": result.first_scan,
        "new_count": len(result.new_listings),
        "total_found": result.total_found,
        "errors": result.errors,
        "new_listings": [item.to_dict() for item in result.new_listings],
    }


def run() -> None:
    uvicorn.run("app.main:api", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()

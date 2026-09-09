from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from app.config import DATA_DIR, DB_PATH
from app.models import Filters, Listing

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS listings (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                title TEXT,
                url TEXT,
                price REAL,
                rooms REAL,
                size_sqm REAL,
                address TEXT,
                district TEXT,
                image_url TEXT,
                postcode TEXT,
                listing_kind TEXT,
                flat_rooms REAL,
                flatmates INTEGER,
                private_landlord INTEGER,
                available_from TEXT,
                available_to TEXT,
                duration_months INTEGER,
                is_sublet INTEGER,
                contactable INTEGER,
                alt_urls TEXT,
                first_seen TEXT,
                last_seen TEXT,
                notified INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                new_count INTEGER,
                total_count INTEGER,
                errors TEXT,
                first_scan INTEGER
            );
            """
        )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(listings)")}
        for name, ddl in (
            ("available_to", "TEXT"),
            ("duration_months", "INTEGER"),
            ("postcode", "TEXT"),
            ("listing_kind", "TEXT"),
            ("flat_rooms", "REAL"),
            ("flatmates", "INTEGER"),
            ("private_landlord", "INTEGER"),
        ):
            if name not in cols:
                conn.execute(f"ALTER TABLE listings ADD COLUMN {name} {ddl}")
        conn.commit()


def load_filters() -> Filters:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
    if not row:
        return Filters()
    return Filters.from_dict(json.loads(row["payload"]))


def save_filters(filters: Filters) -> Filters:
    payload = json.dumps(filters.to_dict(), ensure_ascii=False)
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO settings (id, payload) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
            (payload,),
        )
        conn.commit()
    return filters


def known_ids() -> set[str]:
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT id FROM listings").fetchall()
    return {row["id"] for row in rows}


def clear_listings() -> int:
    """Forget seen ads. Filters stay. Next /scan treats everything as new."""
    with _lock, _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM listings").fetchone()
        count = int(row["n"]) if row else 0
        conn.execute("DELETE FROM listings")
        conn.execute("DELETE FROM scans")
        conn.commit()
    return count


def listing_count() -> int:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM listings").fetchone()
    return int(row["n"]) if row else 0


def upsert_listings(listings: list[Listing], *, mark_notified: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connect() as conn:
        for listing in listings:
            conn.execute(
                """
                INSERT INTO listings (
                    id, provider, title, url, price, rooms, size_sqm, address,
                    district, image_url, postcode, listing_kind, flat_rooms, flatmates,
                    private_landlord, available_from, available_to, duration_months,
                    is_sublet, contactable, alt_urls, first_seen, last_seen, notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    price = excluded.price,
                    rooms = excluded.rooms,
                    size_sqm = excluded.size_sqm,
                    address = excluded.address,
                    district = excluded.district,
                    image_url = excluded.image_url,
                    postcode = excluded.postcode,
                    listing_kind = excluded.listing_kind,
                    flat_rooms = excluded.flat_rooms,
                    flatmates = excluded.flatmates,
                    private_landlord = excluded.private_landlord,
                    available_from = excluded.available_from,
                    available_to = excluded.available_to,
                    duration_months = excluded.duration_months,
                    is_sublet = excluded.is_sublet,
                    contactable = excluded.contactable,
                    alt_urls = excluded.alt_urls,
                    last_seen = excluded.last_seen
                """,
                (
                    listing.id,
                    listing.provider,
                    listing.title,
                    listing.url,
                    listing.price,
                    listing.rooms,
                    listing.size_sqm,
                    listing.address,
                    listing.district,
                    listing.image_url,
                    listing.postcode,
                    listing.listing_kind,
                    listing.flat_rooms,
                    listing.flatmates,
                    int(listing.private_landlord),
                    listing.available_from,
                    listing.available_to,
                    listing.duration_months,
                    int(listing.is_sublet),
                    int(listing.contactable),
                    json.dumps(listing.alt_urls, ensure_ascii=False),
                    now,
                    now,
                    int(mark_notified),
                ),
            )
        conn.commit()


def recent_listings(limit: int = 90) -> list[dict[str, Any]]:
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM listings ORDER BY first_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_listing_dict(row) for row in rows]


def save_scan(
    started_at: str,
    finished_at: str,
    new_count: int,
    total_count: int,
    errors: list[str],
    first_scan: bool,
) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO scans (started_at, finished_at, new_count, total_count, errors, first_scan)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (started_at, finished_at, new_count, total_count, json.dumps(errors, ensure_ascii=False), int(first_scan)),
        )
        conn.commit()


def latest_scan() -> dict[str, Any] | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "new_count": row["new_count"],
        "total_count": row["total_count"],
        "errors": json.loads(row["errors"] or "[]"),
        "first_scan": bool(row["first_scan"]),
    }


def _get(row: sqlite3.Row, column: str) -> Any:
    """Tolerate rows written before a migration added the column."""
    return row[column] if column in row.keys() else None


def _row_to_listing_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "provider": row["provider"],
        "title": row["title"],
        "url": row["url"],
        "price": row["price"],
        "rooms": row["rooms"],
        "size_sqm": row["size_sqm"],
        "address": row["address"],
        "district": row["district"],
        "image_url": row["image_url"],
        "postcode": _get(row, "postcode") or "",
        "listing_kind": _get(row, "listing_kind") or "apartment",
        "flat_rooms": _get(row, "flat_rooms"),
        "flatmates": _get(row, "flatmates"),
        "private_landlord": bool(_get(row, "private_landlord")),
        "available_from": row["available_from"],
        "available_to": _get(row, "available_to"),
        "duration_months": _get(row, "duration_months"),
        "is_sublet": bool(row["is_sublet"]),
        "contactable": bool(row["contactable"]),
        "alt_urls": json.loads(row["alt_urls"] or "[]"),
        "first_seen": row["first_seen"],
        "notified": bool(row["notified"]),
    }

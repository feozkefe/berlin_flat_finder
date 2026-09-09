import importlib

import pytest

from app.models import Listing


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A throwaway database so tests never touch the real one."""
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    db = importlib.reload(importlib.import_module("app.db"))
    db.init_db()
    yield db
    importlib.reload(db)


def _listing(**overrides) -> Listing:
    base = dict(
        id="wg_1",
        provider="wg_gesucht",
        title="Zimmer in 3er WG",
        url="https://example.test/1",
        price=550.0,
        rooms=None,
        size_sqm=15.0,
        address="Weserstraße 1, 12047, Neukölln",
        district="Neukölln",
        postcode="12047",
        listing_kind="wg",
        flatmates=2,
        private_landlord=True,
        available_from="01.10.2026",
        available_to="31.03.2027",
        duration_months=6,
        is_sublet=True,
    )
    base.update(overrides)
    return Listing(**base)


def test_round_trip_keeps_every_field(store):
    store.upsert_listings([_listing()], mark_notified=True)
    (row,) = store.recent_listings()
    assert row["postcode"] == "12047"
    assert row["listing_kind"] == "wg"
    assert row["flatmates"] == 2
    assert row["private_landlord"] is True
    assert row["rooms"] is None
    assert row["available_to"] == "31.03.2027"
    assert row["duration_months"] == 6
    # The stored row must rebuild into the same Listing the scanner ranks on.
    assert Listing.from_dict(row).listing_kind == "wg"


def test_upsert_updates_in_place(store):
    store.upsert_listings([_listing()], mark_notified=True)
    store.upsert_listings([_listing(price=600.0, district="Kreuzberg")], mark_notified=True)
    rows = store.recent_listings()
    assert len(rows) == 1
    assert rows[0]["price"] == 600.0
    assert rows[0]["district"] == "Kreuzberg"


def test_migrates_a_pre_existing_table(tmp_path, monkeypatch):
    import sqlite3

    from app import config

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE listings (id TEXT PRIMARY KEY, provider TEXT, title TEXT, url TEXT,"
            " price REAL, rooms REAL, size_sqm REAL, address TEXT, district TEXT, image_url TEXT,"
            " available_from TEXT, is_sublet INTEGER, contactable INTEGER, alt_urls TEXT,"
            " first_seen TEXT, last_seen TEXT, notified INTEGER)"
        )
        conn.execute(
            "INSERT INTO listings (id, provider, title, url) VALUES ('old_1', 'wg_gesucht', 'Alt', 'u')"
        )

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", path)
    db = importlib.reload(importlib.import_module("app.db"))
    db.init_db()
    try:
        db.upsert_listings([_listing()], mark_notified=True)
        rows = {row["id"]: row for row in db.recent_listings()}
        assert rows["old_1"]["listing_kind"] == "apartment"
        assert rows["wg_1"]["postcode"] == "12047"
    finally:
        importlib.reload(db)

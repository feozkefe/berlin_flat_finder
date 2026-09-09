from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


LISTING_TYPES = ("wg", "apartment", "sublet")
SOURCES = ("wg_gesucht", "kleinanzeigen", "immoscout")
DEFAULT_EXCLUDE = [
    "wbs",
    "wohnberechtigungsschein",
    "tauschwohnung",
    "wohnungstausch",
    "monteurszimmer",
    "monteurswohnung",
]


@dataclass
class Filters:
    districts: list[str] = field(default_factory=list)
    max_rent: int = 1200
    min_rooms: float = 1.0
    min_sqm: int = 0
    listing_types: list[str] = field(default_factory=lambda: ["wg", "apartment", "sublet"])
    sources: list[str] = field(default_factory=lambda: list(SOURCES))
    interval_hours: int = 12
    start_from: str = ""
    min_months: int = 1
    max_months: int = 0
    telegram_chat_id: str = ""
    exclude_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Filters:
        base = cls()
        if not data:
            return base
        for key in (
            "districts",
            "max_rent",
            "min_rooms",
            "min_sqm",
            "listing_types",
            "sources",
            "interval_hours",
            "start_from",
            "min_months",
            "max_months",
            "telegram_chat_id",
            "exclude_keywords",
            "enabled",
        ):
            if key in data and data[key] is not None:
                setattr(base, key, data[key])
        if base.interval_hours not in (12, 24):
            base.interval_hours = 12
        try:
            base.min_months = int(base.min_months or 0)
            base.max_months = int(base.max_months or 0)
        except (TypeError, ValueError):
            base.min_months = 1
            base.max_months = 0
        if base.min_months <= 0:
            base.min_months = 1
        base.start_from = str(base.start_from or "").strip()
        base.listing_types = [t for t in base.listing_types if t in LISTING_TYPES] or list(LISTING_TYPES)
        base.sources = [s for s in base.sources if s in SOURCES] or list(SOURCES)
        return base


@dataclass
class Listing:
    id: str
    provider: str
    title: str
    url: str
    price: float | None = None
    rooms: float | None = None
    size_sqm: float | None = None
    address: str = ""
    district: str = ""
    image_url: str | None = None
    postcode: str = ""
    # "wg" = a room in a shared flat, "apartment" = a whole place. Room counts and
    # square metres mean different things for the two, so filters need to know.
    listing_kind: str = "apartment"
    flat_rooms: float | None = None
    flatmates: int | None = None
    private_landlord: bool = False
    available_from: str | None = None
    available_to: str | None = None
    duration_months: int | None = None
    is_sublet: bool = False
    contactable: bool = True
    alt_urls: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Listing:
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class ScanResult:
    started_at: str
    finished_at: str
    new_listings: list[Listing]
    total_found: int
    errors: list[str]
    first_scan: bool = False

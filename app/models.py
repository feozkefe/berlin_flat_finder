from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


LISTING_TYPES = ("wg", "apartment", "sublet")
SOURCES = ("wg_gesucht", "kleinanzeigen", "immoscout")
DEFAULT_EXCLUDE = [
    "wbs erforderlich",
    "nur mit wbs",
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
            "telegram_chat_id",
            "exclude_keywords",
            "enabled",
        ):
            if key in data and data[key] is not None:
                setattr(base, key, data[key])
        if base.interval_hours not in (12, 24):
            base.interval_hours = 12
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
    available_from: str | None = None
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

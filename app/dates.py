from __future__ import annotations

import re
from datetime import date, timedelta

from app.models import Listing

_DE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTHS = re.compile(r"(\d{1,2})\s*(?:-\s*(\d{1,2})\s*)?(?:monat|months?)\b", re.I)
_ANY = {"0", "sofort", "hemen", "anytime", "farketmez", "fark etmez", "ab sofort", "-"}


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    raw = text.strip()
    if not raw or raw in {"00.00.0000", "0"}:
        return None
    folded = raw.lower()
    if any(word in folded for word in ("sofort", "immediately", "ab sofort", "hemen", "now")):
        return date.today()
    match = _DE.search(raw) or _ISO.search(raw)
    if not match:
        return None
    if match.re is _DE:
        day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    else:
        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_user_start(text: str) -> str:
    """Empty string = no start filter. Otherwise ISO date."""
    raw = (text or "").strip()
    if raw.lower() in {"0", "anytime", "farketmez", "fark etmez", "-"}:
        return ""
    parsed = parse_date(raw)
    return parsed.isoformat() if parsed else "invalid"


def parse_user_months(text: str) -> tuple[int, int] | None:
    raw = (text or "").strip().lower().replace(" ", "")
    if raw in _ANY:
        return (0, 0)
    match = re.fullmatch(r"(\d{1,2})(?:[-/](\d{1,2}))?", raw)
    if not match:
        return None
    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) else 0
    if low > 36 or high > 36:
        return None
    if high and high < low:
        return None
    return (low, high)


def months_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    return max(1, (end.year - start.year) * 12 + end.month - start.month)


def extract_duration_months(text: str) -> int | None:
    match = _MONTHS.search(text or "")
    if not match:
        return None
    return int(match.group(1))


def fill_timing(listing: Listing, extra_text: str = "") -> Listing:
    blob = f"{listing.title} {listing.address} {listing.available_from or ''} {extra_text}"
    if not listing.available_from:
        found = parse_date(blob)
        if found:
            listing.available_from = found.strftime("%d.%m.%Y")
    start = parse_date(listing.available_from)
    end = parse_date(listing.available_to)
    if listing.duration_months is None:
        if start and end:
            listing.duration_months = months_between(start, end)
        else:
            listing.duration_months = extract_duration_months(blob)
    return listing


def timing_passes(listing: Listing, start_from: str, min_months: int, max_months: int) -> bool:
    if start_from:
        needed = parse_date(start_from)
        ready = parse_date(listing.available_from)
        if needed and ready and ready > needed + timedelta(days=14):
            return False
    if min_months and listing.duration_months is not None and listing.duration_months < min_months:
        return False
    if max_months:
        if listing.duration_months is None:
            # No end date = unbefristet. Too long if user asked for a max.
            return False
        if listing.duration_months > max_months:
            return False
    return True


def today_iso() -> str:
    return date.today().isoformat()

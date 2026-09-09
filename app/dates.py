from __future__ import annotations

import re
from datetime import date, timedelta

from app.models import Listing

_DE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_ANY = {"0", "sofort", "hemen", "anytime", "farketmez", "fark etmez", "ab sofort", "-"}

# German plurals: "6 Monate" / "6 Monaten" must match, but "3 Monatsmieten"
# (a deposit, not a duration) must not.
_MONTHS = re.compile(
    r"(?<![.,\d])(\d{1,2})\s*(?:[-–/]\s*(\d{1,2})\s*)?(?:monat(?:e|en)?|months?|mo\b)(?![a-z])",
    re.I,
)
# "3 Monatsmieten Kaution", "Kaution 2 Monate" — money, not tenancy length.
_DEPOSIT_NEAR = re.compile(r"kaution|deposit|monatsmiete|mietsicherheit|bürgschaft|buergschaft", re.I)

# A date only means "move-in" when an availability word introduces it. Free text is
# full of unrelated dates (posted-on stamps, "Baujahr 1970", "renoviert 2019").
_AVAILABLE_CUE = (
    r"(?:ab(?:\s+dem)?|frei\s+ab|verf(?:ü|ue)gbar(?:\s+ab)?|bezugsfrei(?:\s+ab)?|beziehbar\s+ab"
    r"|einzug(?:\s+ab)?|vermietung\s+ab|zum|per|available(?:\s+from)?|from|move[-\s]?in)"
)
_AVAILABLE_DATE = re.compile(
    _AVAILABLE_CUE + r"\s*:?\s*(\d{1,2}\.\d{1,2}\.?(?:\d{4}|\d{2})?|\d{4}-\d{2}-\d{2})",
    re.I,
)
_AVAILABLE_NOW = re.compile(
    r"(?:ab\s+sofort|sofort\s+(?:frei|beziehbar|verf(?:ü|ue)gbar|bezugsfrei)|sofort\s+zu\s+vermieten"
    r"|available\s+(?:now|immediately)|immediately\s+available|kurzfristig\s+frei)",
    re.I,
)
# Sublet windows: "01.10.-30.11.", "vom 1.10. bis 31.12.2026"
_DATE_RANGE = re.compile(
    r"(\d{1,2}\.\d{1,2}\.?(?:\d{4})?)\s*(?:-|–|bis|to|until|till)\s*(\d{1,2}\.\d{1,2}\.?(?:\d{4})?)",
    re.I,
)

# An ad may sit online for a while, and posters write "ab 01.09" in October.
_MAX_PAST_DAYS = 45
_MAX_FUTURE_DAYS = 730


def parse_date(text: str | None) -> date | None:
    """Parse a full, explicit date. Does not interpret 'sofort' — see parse_available_from."""
    if not text:
        return None
    raw = text.strip()
    if not raw or raw in {"00.00.0000", "0"}:
        return None
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


def _parse_loose_date(raw: str, today: date | None = None) -> date | None:
    """Accepts 01.10.2026, 01.10.26 and the very common year-less '1.10.'."""
    today = today or date.today()
    raw = raw.strip().rstrip(".")
    iso = _ISO.search(raw)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    parts = [p for p in raw.split(".") if p]
    if len(parts) < 2:
        return None
    try:
        day, month = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if len(parts) >= 3:
        try:
            year = int(parts[2])
        except ValueError:
            return None
        if year < 100:
            year += 2000
    else:
        # No year given: pick the nearest sensible one.
        year = today.year
        try:
            if date(year, month, day) < today - timedelta(days=_MAX_PAST_DAYS):
                year += 1
        except ValueError:
            return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _plausible(value: date | None, today: date | None = None) -> date | None:
    today = today or date.today()
    if not value:
        return None
    if value < today - timedelta(days=_MAX_PAST_DAYS):
        return None
    if value > today + timedelta(days=_MAX_FUTURE_DAYS):
        return None
    return value


def parse_available_from(text: str, today: date | None = None) -> date | None:
    """Move-in date, only when the text actually says it is one."""
    today = today or date.today()
    if not text:
        return None
    match = _AVAILABLE_DATE.search(text)
    if match:
        found = _plausible(_parse_loose_date(match.group(1), today), today)
        if found:
            return found
    if _AVAILABLE_NOW.search(text):
        return today
    return None


def parse_user_start(text: str) -> str:
    """Empty string = no start filter. Otherwise ISO date."""
    raw = (text or "").strip()
    if raw.lower() in {"0", "anytime", "farketmez", "fark etmez", "-"}:
        return ""
    if raw.lower() in {"sofort", "hemen", "now", "ab sofort", "immediately"}:
        return date.today().isoformat()
    parsed = parse_date(raw) or _parse_loose_date(raw)
    return parsed.isoformat() if parsed else "invalid"


def parse_user_months(text: str) -> tuple[int, int] | None:
    raw = (text or "").strip().lower()
    raw = re.sub(r"\b(min|max|at least|en az|ay|month|months|monat|monate|monaten)\b", "", raw)
    raw = raw.replace(" ", "")
    if raw in _ANY or raw == "":
        return (1, 0)
    match = re.fullmatch(r"(\d{1,2})(?:[-/](\d{1,2}))?", raw)
    if not match:
        return None
    low = max(1, int(match.group(1)))
    high = int(match.group(2)) if match.group(2) else 0
    if low > 36 or high > 36:
        return None
    if high and high < low:
        return None
    return (low, high)


def months_between(start: date, end: date) -> int:
    """Rounded to whole months: 01.10.-30.11. is two months, not one."""
    if end <= start:
        return 0
    return max(1, round((end - start).days / 30.44))


def extract_duration_months(text: str) -> int | None:
    """Tenancy length in months, ignoring deposit amounts quoted in months."""
    for match in _MONTHS.finditer(text or ""):
        window = text[max(0, match.start() - 40) : match.end() + 40]
        if _DEPOSIT_NEAR.search(window):
            continue
        low = int(match.group(1))
        if not 1 <= low <= 36:
            continue
        return low
    return None


def extract_date_range(text: str, today: date | None = None) -> tuple[date, date] | None:
    match = _DATE_RANGE.search(text or "")
    if not match:
        return None
    start = _plausible(_parse_loose_date(match.group(1), today), today)
    end = _parse_loose_date(match.group(2), today)
    if not start or not end or end <= start:
        return None
    return (start, end)


def fill_timing(listing: Listing, extra_text: str = "") -> Listing:
    """Derive move-in date and tenancy length from whatever the source gave us."""
    blob = f"{listing.title} {extra_text}"

    if not listing.available_from:
        found = parse_available_from(blob)
        if not found:
            window = extract_date_range(blob)
            if window:
                found = window[0]
                if not listing.available_to:
                    listing.available_to = window[1].strftime("%d.%m.%Y")
        if found:
            listing.available_from = found.strftime("%d.%m.%Y")
    elif not _plausible(parse_date(listing.available_from)):
        # Source gave a stale date (ad reposted, or 01.01.1970 style junk).
        listing.available_from = None

    if not listing.available_to:
        window = extract_date_range(blob)
        if window:
            listing.available_to = window[1].strftime("%d.%m.%Y")

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

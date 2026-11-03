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
# "2 Wochen", "3 weeks", "2 hafta" — short sublets are quoted in weeks.
_WEEKS = re.compile(r"(?<![.,\d])(\d{1,2})\s*(?:wochen|woche|weeks?|wks?|hafta)(?![a-z])", re.I)
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
# How far a listing's move-in date may drift from the user's, either way.
_START_TOLERANCE_DAYS = 14


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


HALF_MONTH = 0.5  # "2 weeks" — the shortest stay the filters know about.


def normalize_months(value: float | int | str | None, *, allow_zero: bool) -> float | int:
    """Durations are whole months, plus 0.5 for a two-week stay."""
    try:
        number = float(str(value).replace(",", ".")) if value not in (None, "") else 0.0
    except ValueError:
        number = 0.0
    if number <= 0:
        return 0 if allow_zero else 1
    if number < 1:
        return HALF_MONTH
    return int(round(number))


def format_months(value: float | int | None) -> str:
    if not value:
        return ""
    if value < 1:
        return "2 weeks"
    count = int(value)
    return f"{count} month" + ("s" if count != 1 else "")


_HALF_WORDS = {"half", "yarım", "yarim", "0.5", "0,5", ".5", "1/2", "½", "2w", "2wk", "2wks"}


def _user_months_token(token: str) -> float | None:
    """One side of '6-12': '6', '0.5', '2w', '2weeks', '2hafta', 'yarım'."""
    if token in _HALF_WORDS:
        return HALF_MONTH
    weeks = re.fullmatch(r"(\d{1,2})(?:w|wk|wks|week|weeks|hafta|woche|wochen)", token)
    if weeks:
        count = int(weeks.group(1))
        if count <= 0:
            return None
        return HALF_MONTH if count < 4 else float(max(1, round(count / 4.345)))
    number = re.fullmatch(r"(\d{1,2})(?:[.,](\d))?", token)
    if not number:
        return None
    return float(f"{number.group(1)}.{number.group(2) or 0}")


def parse_user_months(text: str) -> tuple[float | int, float | int] | None:
    raw = (text or "").strip().lower()
    raw = re.sub(r"\b(min|max|at least|en az|ay|month|months|monat|monate|monaten)\b", "", raw)
    raw = raw.replace(" ", "")
    if raw in _ANY or raw == "":
        return (1, 0)
    if raw in _HALF_WORDS:
        # "1/2" means half a month here, not a 1-2 month range.
        return (HALF_MONTH, 0)
    parts = re.split(r"[-–]|/(?!2$)", raw, maxsplit=1)
    low_raw = _user_months_token(parts[0])
    high_raw = _user_months_token(parts[1]) if len(parts) > 1 else 0.0
    if low_raw is None or high_raw is None:
        return None
    if low_raw > 36 or high_raw > 36:
        return None
    low = normalize_months(low_raw, allow_zero=False)
    high = normalize_months(high_raw, allow_zero=True)
    if high and high < low:
        return None
    return (low, high)


def months_between(start: date, end: date) -> float | int:
    """Rounded to whole months: 01.10.-30.11. is two months, not one.

    Stays under a month count as 0.5 (about two weeks) when they last at least
    12 days, and as their real fraction otherwise, so a one-week sublet stays
    below a two-week minimum.
    """
    if end <= start:
        return 0
    days = (end - start).days
    if days >= 23:
        return max(1, round(days / 30.44))
    if days >= 12:
        return HALF_MONTH
    return round(days / 30.44, 2)


def extract_duration_months(text: str) -> float | int | None:
    """Tenancy length in months, ignoring deposit amounts quoted in months."""
    for match in _MONTHS.finditer(text or ""):
        window = text[max(0, match.start() - 40) : match.end() + 40]
        if _DEPOSIT_NEAR.search(window):
            continue
        low = int(match.group(1))
        if not 1 <= low <= 36:
            continue
        return low
    for match in _WEEKS.finditer(text or ""):
        weeks = int(match.group(1))
        if not 1 <= weeks <= 52:
            continue
        if weeks >= 4:
            return max(1, round(weeks / 4.345))
        return HALF_MONTH if weeks >= 2 else round(weeks * 7 / 30.44, 2)
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


def timing_passes(listing: Listing, start_from: str, min_months: float, max_months: float) -> bool:
    if start_from:
        needed = parse_date(start_from)
        ready = parse_date(listing.available_from)
        # A flat free from October is let in October — useless if you move in December.
        if needed and ready and abs(ready - needed) > timedelta(days=_START_TOLERANCE_DAYS):
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

from __future__ import annotations

import re

from app.districts import fold
from app.models import Listing

_STREET_RE = re.compile(
    r"([a-z]+(?:\s+[a-z]+)*\s+(?:str|strasse|platz|allee|weg|ufer|damm|ring|gasse|chaussee))\s*\d*",
)
_PLZ_RE = re.compile(r"\b(1[0-4]\d{3})\b")
_SUBLET_WORDS = (
    "zwischenmiete",
    "untermiete",
    "befristet",
    "sublet",
    "temporary",
    "zeitmiete",
    "befristete miete",
    "limited",
)


def extract_plz(text: str) -> str | None:
    match = _PLZ_RE.search(text or "")
    return match.group(1) if match else None


def normalize_street(address: str) -> str | None:
    folded = fold(address)
    folded = folded.replace("strasse", "str").replace("str.", "str")
    match = _STREET_RE.search(folded)
    if match:
        street = match.group(1)
        return re.sub(r"\s+", " ", street.replace("strasse", "str")).strip()
    return None


def looks_like_sublet(text: str) -> bool:
    haystack = fold(text)
    return any(word in haystack for word in _SUBLET_WORDS)


def looks_like_wanted_ad(title: str) -> bool:
    folded = fold(title)
    return folded.startswith("suche") or folded.startswith("gesucht") or "suche nachmieter" in folded


def contains_excluded(text: str, keywords: list[str]) -> bool:
    haystack = fold(text)
    return any(fold(keyword) in haystack for keyword in keywords if keyword.strip())


def _close(a: float | None, b: float | None, tolerance: float) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance


def same_listing(left: Listing, right: Listing) -> bool:
    if left.provider == right.provider:
        return False

    street_a = normalize_street(left.address)
    street_b = normalize_street(right.address)
    plz_a = extract_plz(f"{left.address} {left.title}")
    plz_b = extract_plz(f"{right.address} {right.title}")
    price_close = _close(left.price, right.price, 80)
    size_close = _close(left.size_sqm, right.size_sqm, 8)
    rooms_close = _close(left.rooms, right.rooms, 0.5)

    if street_a and street_b and street_a == street_b:
        return price_close or size_close or rooms_close

    if plz_a and plz_b and plz_a == plz_b and price_close and (size_close or rooms_close):
        return True

    return False


def attach_cross_matches(listings: list[Listing]) -> list[Listing]:
    """If an ImmoScout ad also exists on WG/Kleinanzeigen, surface that writable URL."""
    for listing in listings:
        listing.alt_urls = []

    for i, left in enumerate(listings):
        for right in listings[i + 1 :]:
            if not same_listing(left, right):
                continue
            left.alt_urls.append({"provider": right.provider, "url": right.url, "title": right.title})
            right.alt_urls.append({"provider": left.provider, "url": left.url, "title": left.title})

    return listings

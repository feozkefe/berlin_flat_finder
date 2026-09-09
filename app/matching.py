from __future__ import annotations

import re

from app.districts import extract_plz, fold
from app.models import Listing

_STREET_RE = re.compile(
    r"([a-z]+(?:\s+[a-z]+)*\s+(?:str|strasse|platz|allee|weg|ufer|damm|ring|gasse|chaussee))\s*\d*",
)
_NEGATIONS =("ohne", "kein", "keine", "nicht", "without", "no")
_WANTED_PHRASES = (
    "suche nachmieter",
    "wohnung gesucht",
    "zimmer gesucht",
    "wg zimmer gesucht",
    "nachmieter gesucht",
    "suche dringend",
)
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
    """Someone looking for a flat, not offering one."""
    folded = fold(title)
    if folded.startswith(("suche", "gesucht", "wir suchen", "ich suche", "looking for")):
        return True
    return any(phrase in folded for phrase in _WANTED_PHRASES)


def contains_excluded(text: str, keywords: list[str]) -> bool:
    haystack = fold(text)
    for keyword in keywords:
        folded = fold(keyword)
        if not folded:
            continue
        if any(not _is_negated(haystack, at) for at in _positions(haystack, folded)):
            return True
    return False


def _positions(haystack: str, needle: str) -> list[int]:
    found, at = [], haystack.find(needle)
    while at != -1:
        found.append(at)
        at = haystack.find(needle, at + 1)
    return found


def _is_negated(haystack: str, at: int) -> bool:
    """'ohne WBS' / 'kein WBS' are selling points, not a reason to drop the ad."""
    before = haystack[max(0, at - 20) : at]
    return any(word in before for word in _NEGATIONS)


def _close(a: float | None, b: float | None, tolerance: float) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance


def same_listing(left: Listing, right: Listing) -> bool:
    if left.provider == right.provider:
        return False

    street_a = normalize_street(left.address)
    street_b = normalize_street(right.address)
    plz_a = left.postcode or extract_plz(f"{left.address} {left.title}")
    plz_b = right.postcode or extract_plz(f"{right.address} {right.title}")
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

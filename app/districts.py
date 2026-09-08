from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def fold(text: str) -> str:
    """Lowercase + strip diacritics so 'Schöneberg' matches 'schoneberg'."""
    text = (text or "").replace("ß", "ss").replace("ẞ", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@dataclass(frozen=True)
class District:
    id: str
    name: str
    bezirk: str
    aliases: tuple[str, ...]
    immoscout_geocode: str | None = None


# Popular Kieze first. Matching is alias-based against title + address.
DISTRICTS: tuple[District, ...] = (
    District("mitte", "Mitte", "Mitte", ("mitte",), "/de/berlin/berlin/mitte-mitte"),
    District("tiergarten", "Tiergarten", "Mitte", ("tiergarten",), "/de/berlin/berlin/tiergarten-tiergarten"),
    District("moabit", "Moabit", "Mitte", ("moabit",), "/de/berlin/berlin/moabit-moabit"),
    District("wedding", "Wedding", "Mitte", ("wedding",), "/de/berlin/berlin/wedding-wedding"),
    District("gesundbrunnen", "Gesundbrunnen", "Mitte", ("gesundbrunnen",), "/de/berlin/berlin/gesundbrunnen-gesundbrunnen"),
    District(
        "friedrichshain",
        "Friedrichshain",
        "Friedrichshain-Kreuzberg",
        ("friedrichshain", "fhain", "boxhagener", "simon dach"),
        "/de/berlin/berlin/friedrichshain-friedrichshain",
    ),
    District(
        "kreuzberg",
        "Kreuzberg",
        "Friedrichshain-Kreuzberg",
        ("kreuzberg", "goerlitzer", "wrangelkiez", "bergmannkiez"),
        "/de/berlin/berlin/kreuzberg-kreuzberg",
    ),
    District(
        "prenzlauer_berg",
        "Prenzlauer Berg",
        "Pankow",
        ("prenzlauer berg", "prenzlberg", "helmholtzkiez", "kollwitzkiez"),
        "/de/berlin/berlin/prenzlauer-berg-prenzlauer-berg",
    ),
    District("pankow", "Pankow", "Pankow", ("pankow",), "/de/berlin/berlin/pankow-pankow"),
    District("weissensee", "Weißensee", "Pankow", ("weissensee", "weisensee"), "/de/berlin/berlin/weissensee-weissensee"),
    District(
        "neukoelln",
        "Neukölln",
        "Neukölln",
        ("neukoelln", "neukolln", "reuterkiez", "schillerkiez", "weserkiez"),
        "/de/berlin/berlin/neukoelln-neukoelln",
    ),
    District("britz", "Britz", "Neukölln", ("britz",), "/de/berlin/berlin/britz-britz"),
    District(
        "charlottenburg",
        "Charlottenburg",
        "Charlottenburg-Wilmersdorf",
        ("charlottenburg",),
        "/de/berlin/berlin/charlottenburg-charlottenburg",
    ),
    District(
        "wilmersdorf",
        "Wilmersdorf",
        "Charlottenburg-Wilmersdorf",
        ("wilmersdorf",),
        "/de/berlin/berlin/wilmersdorf-wilmersdorf",
    ),
    District(
        "schoeneberg",
        "Schöneberg",
        "Tempelhof-Schöneberg",
        ("schoeneberg", "schoneberg", "akazienkiez"),
        "/de/berlin/berlin/schoeneberg-schoeneberg",
    ),
    District("tempelhof", "Tempelhof", "Tempelhof-Schöneberg", ("tempelhof",), "/de/berlin/berlin/tempelhof-tempelhof"),
    District("steglitz", "Steglitz", "Steglitz-Zehlendorf", ("steglitz",), "/de/berlin/berlin/steglitz-steglitz"),
    District("zehlendorf", "Zehlendorf", "Steglitz-Zehlendorf", ("zehlendorf",), "/de/berlin/berlin/zehlendorf-zehlendorf"),
    District("treptow", "Treptow", "Treptow-Köpenick", ("treptow", "alt treptow", "plaenterwald"), "/de/berlin/berlin/alt-treptow-alt-treptow"),
    District("koepenick", "Köpenick", "Treptow-Köpenick", ("koepenick", "kopenick"), "/de/berlin/berlin/koepenick-koepenick"),
    District("lichtenberg", "Lichtenberg", "Lichtenberg", ("lichtenberg",), "/de/berlin/berlin/lichtenberg-lichtenberg"),
    District("friedrichsfelde", "Friedrichsfelde", "Lichtenberg", ("friedrichsfelde",), "/de/berlin/berlin/friedrichsfelde-friedrichsfelde"),
    District("reinickendorf", "Reinickendorf", "Reinickendorf", ("reinickendorf",), "/de/berlin/berlin/reinickendorf-reinickendorf"),
    District("spandau", "Spandau", "Spandau", ("spandau",), "/de/berlin/berlin/spandau-spandau"),
    District("marzahn", "Marzahn", "Marzahn-Hellersdorf", ("marzahn",), "/de/berlin/berlin/marzahn-marzahn"),
)

DISTRICT_BY_ID = {d.id: d for d in DISTRICTS}

# Longer aliases first so "prenzlauer berg" wins over a later short token.
_ALIAS_INDEX: list[tuple[str, District]] = sorted(
    ((fold(alias), district) for district in DISTRICTS for alias in (*district.aliases, district.name)),
    key=lambda item: len(item[0]),
    reverse=True,
)


def detect_district(text: str) -> District | None:
    haystack = f" {fold(text)} "
    for alias, district in _ALIAS_INDEX:
        if f" {alias} " in haystack:
            return district
    return None


def matches_selected(text: str, selected_ids: list[str]) -> bool:
    if not selected_ids:
        return True
    found = detect_district(text)
    if found and found.id in selected_ids:
        return True
    # Keep listings with no readable district so we don't drop good ads.
    return found is None


def public_districts() -> list[dict]:
    return [
        {"id": d.id, "name": d.name, "bezirk": d.bezirk}
        for d in DISTRICTS
    ]

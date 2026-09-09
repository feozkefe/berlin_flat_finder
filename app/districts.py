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
    District("moabit", "Moabit", "Mitte", ("moabit",), None),
    District("wedding", "Wedding", "Mitte", ("wedding",), "/de/berlin/berlin/wedding-wedding"),
    District("gesundbrunnen", "Gesundbrunnen", "Mitte", ("gesundbrunnen",), None),
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
    District("britz", "Britz", "Neukölln", ("britz",), None),
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
    District("treptow", "Treptow", "Treptow-Köpenick", ("treptow", "alt treptow", "plaenterwald"), None),
    District("koepenick", "Köpenick", "Treptow-Köpenick", ("koepenick", "kopenick"), "/de/berlin/berlin/koepenick-koepenick"),
    District("lichtenberg", "Lichtenberg", "Lichtenberg", ("lichtenberg",), "/de/berlin/berlin/lichtenberg-lichtenberg"),
    District("friedrichsfelde", "Friedrichsfelde", "Lichtenberg", ("friedrichsfelde",), None),
    District("reinickendorf", "Reinickendorf", "Reinickendorf", ("reinickendorf",), "/de/berlin/berlin/reinickendorf-reinickendorf"),
    District("spandau", "Spandau", "Spandau", ("spandau",), "/de/berlin/berlin/spandau-spandau"),
    District("marzahn", "Marzahn", "Marzahn-Hellersdorf", ("marzahn",), "/de/berlin/berlin/marzahn-marzahn"),
)

DISTRICT_BY_ID = {d.id: d for d in DISTRICTS}

# Berlin postcodes run 10115-14199. A PLZ is the only location signal all three
# sources agree on, so it outranks free text like WG-Gesucht's "direkt an der U5".
# Each tuple must list *every* PLZ of that district, otherwise strict district
# filtering in matches_selected() would drop good ads.
PLZ_BY_DISTRICT: dict[str, tuple[str, ...]] = {
    "mitte": ("10115", "10117", "10119", "10178", "10179"),
    "tiergarten": ("10555", "10557", "10785", "10787"),
    "moabit": ("10551", "10553", "10555", "10557", "10559"),
    "wedding": ("13347", "13349", "13351", "13353"),
    "gesundbrunnen": ("13355", "13357", "13359", "13409"),
    "friedrichshain": ("10243", "10245", "10247", "10249"),
    "kreuzberg": ("10961", "10963", "10965", "10967", "10969", "10997", "10999"),
    "prenzlauer_berg": ("10119", "10405", "10407", "10409", "10435", "10437", "10439"),
    "pankow": ("13187", "13189"),
    "weissensee": ("13086", "13088"),
    "neukoelln": ("12043", "12045", "12047", "12049", "12051", "12053", "12055", "12057", "12059"),
    "britz": ("12347", "12349", "12359"),
    "charlottenburg": ("10585", "10587", "10589", "10623", "10625", "10627", "10629", "14057", "14059"),
    "wilmersdorf": ("10707", "10709", "10711", "10713", "10715", "10717", "10719", "14193", "14197", "14199"),
    "schoeneberg": ("10777", "10779", "10781", "10783", "10823", "10825", "10827", "10829", "12157", "12159", "12161"),
    "tempelhof": ("12099", "12101", "12103", "12105", "12107", "12109"),
    "steglitz": ("12163", "12165", "12167", "12169", "12203", "12205", "12207", "12209", "12247", "12249"),
    "zehlendorf": ("14109", "14129", "14163", "14165", "14167", "14169", "14195"),
    # Split along the pre-2001 Bezirke, which is what people still mean by the
    # two names: Oberschöneweide (12459) is Köpenick, Adlershof (12489) is Treptow.
    "treptow": ("12435", "12437", "12439", "12487", "12489", "12524", "12526"),
    "koepenick": ("12459", "12527", "12555", "12557", "12559", "12587", "12589"),
    "lichtenberg": ("10318", "10365", "10367", "10369", "13051", "13053", "13055", "13057", "13059"),
    "friedrichsfelde": ("10315", "10317", "10319"),
    "reinickendorf": (
        "13403", "13405", "13407", "13435", "13437", "13439", "13465", "13467",
        "13469", "13503", "13505", "13507", "13509",
    ),
    "spandau": (
        "13581", "13583", "13585", "13587", "13589", "13591", "13593", "13595",
        "13597", "13599", "13627", "13629", "14052", "14053", "14089",
    ),
    "marzahn": ("12679", "12681", "12683", "12685", "12687", "12689"),
}

_DISTRICTS_BY_PLZ: dict[str, tuple[District, ...]] = {}
for _district_id, _codes in PLZ_BY_DISTRICT.items():
    for _code in _codes:
        _DISTRICTS_BY_PLZ.setdefault(_code, ())
        _DISTRICTS_BY_PLZ[_code] += (DISTRICT_BY_ID[_district_id],)

# The blocks Berlin's postcodes fall in. Lets us tell "a Berlin address we do not
# track" (reject it when districts are selected) from "not a real postcode".
_BERLIN_PLZ_RANGES: tuple[tuple[int, int], ...] = (
    (10115, 10179),
    (10243, 10249),
    (10315, 10369),
    (10405, 10439),
    (10551, 10559),
    (10585, 10629),
    (10707, 10719),
    (10777, 10789),
    (10823, 10829),
    (10961, 10999),
    (12043, 12109),
    (12157, 12209),
    (12247, 12359),
    (12435, 12689),
    (13051, 13129),
    (13156, 13189),
    (13347, 13359),
    (13403, 13469),
    (13503, 13629),
    (14050, 14199),
)

_PLZ_RE = re.compile(r"\b(\d{5})\b")


def extract_plz(text: str) -> str | None:
    """First Berlin postcode in the text, or None."""
    for match in _PLZ_RE.finditer(text or ""):
        if is_berlin_plz(match.group(1)):
            return match.group(1)
    return None


def is_berlin_plz(plz: str | None) -> bool:
    """True only for codes Berlin actually uses, so typos like '12000' stay unknown."""
    if not plz or len(plz) != 5 or not plz.isdigit():
        return False
    code = int(plz)
    return any(low <= code <= high for low, high in _BERLIN_PLZ_RANGES)


def districts_for_plz(plz: str | None) -> tuple[District, ...]:
    return _DISTRICTS_BY_PLZ.get(plz or "", ())


# Longer aliases first so "prenzlauer berg" wins over a later short token.
_ALIAS_INDEX: list[tuple[str, District]] = sorted(
    ((fold(alias), district) for district in DISTRICTS for alias in (*district.aliases, district.name)),
    key=lambda item: len(item[0]),
    reverse=True,
)


def detect_district(text: str, plz: str | None = None) -> District | None:
    """Postcode wins over free text; ad copy name-drops neighbourhoods it isn't in."""
    by_plz = districts_for_plz(plz or extract_plz(text))
    if by_plz:
        named = detect_by_alias(text)
        # A PLZ can span two Ortsteile (10119 is Mitte and Prenzlauer Berg).
        # Let the ad's own wording break the tie, but only within that PLZ.
        if named and named in by_plz:
            return named
        return by_plz[0]
    return detect_by_alias(text)


def detect_by_alias(text: str) -> District | None:
    haystack = f" {fold(text)} "
    for alias, district in _ALIAS_INDEX:
        if f" {alias} " in haystack:
            return district
    return None


def matches_selected(text: str, selected_ids: list[str], plz: str | None = None) -> bool:
    if not selected_ids:
        return True

    plz = plz or extract_plz(text)
    by_plz = districts_for_plz(plz)
    if by_plz:
        # PLZ_BY_DISTRICT lists every code per district, so a postcode we recognise
        # that sits outside the selection is a definite miss - not an unknown.
        return any(d.id in selected_ids for d in by_plz)

    if is_berlin_plz(plz):
        # A real Berlin code outside every tracked district: a definite miss.
        return False

    # Not a postcode we can place at all - fall back to what the ad text says
    # rather than dropping an otherwise good listing.
    found = detect_by_alias(text)
    if found:
        return found.id in selected_ids
    # No postcode and no district name at all: keep it rather than lose a good ad.
    return True


def public_districts() -> list[dict]:
    return [
        {"id": d.id, "name": d.name, "bezirk": d.bezirk}
        for d in DISTRICTS
    ]

from app.districts import PLZ_BY_DISTRICT, detect_district, matches_selected


def test_detects_kiez_aliases():
    assert detect_district("Schöne 2 Zi in Prenzlauer Berg, Kollwitzkiez").id == "prenzlauer_berg"
    assert detect_district("FHAIN Altbau nahe Boxhagener Platz").id == "friedrichshain"
    assert detect_district("Neukölln Reuterkiez").id == "neukoelln"


def test_postcode_beats_name_dropping():
    # Posters advertise the Kiez they wish they were in. The PLZ is the truth.
    listing = "Schönes Zimmer in Neukölln - nähe Görlitzer Park"
    assert detect_district(listing).id == "neukoelln"
    assert detect_district(listing, "12435").id == "treptow"


def test_postcode_resolves_freetext_districts():
    # WG-Gesucht's district_custom is whatever the poster typed.
    assert detect_district("direkt an der U5, 12589 Berlin").id == "koepenick"


def test_selected_districts():
    assert matches_selected("Kreuzberg Wrangelkiez", ["kreuzberg"])
    assert not matches_selected("Spandau Altstadt", ["kreuzberg", "neukoelln"])
    assert matches_selected("Berlin, genaue Lage auf Anfrage", ["kreuzberg"])


def test_selected_districts_reject_by_postcode():
    # This is the leak that filled a Neukölln search with Reinickendorf ads.
    assert not matches_selected("WG Zimmer, 13503 Berlin", ["neukoelln", "kreuzberg"])
    assert matches_selected("WG Zimmer, 12047 Berlin", ["neukoelln", "kreuzberg"])


def test_unknown_postcode_falls_back_to_text():
    # "12000" is not a real code; do not throw away an otherwise good ad.
    assert matches_selected("Wohnungstausch Neukölln, 12000 Berlin", ["neukoelln"])


def test_treptow_and_koepenick_split_on_the_old_bezirk_line():
    assert detect_district("Berlin", "12489").id == "treptow"
    assert detect_district("Berlin", "12459").id == "koepenick"


def test_postcode_table_has_no_duplicate_entries_per_district():
    for district_id, codes in PLZ_BY_DISTRICT.items():
        assert len(codes) == len(set(codes)), district_id
        assert all(len(code) == 5 and code.isdigit() for code in codes), district_id

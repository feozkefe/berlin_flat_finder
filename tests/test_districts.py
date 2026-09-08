from app.districts import detect_district, matches_selected


def test_detects_kiez_aliases():
    assert detect_district("Schöne 2 Zi in Prenzlauer Berg, Kollwitzkiez").id == "prenzlauer_berg"
    assert detect_district("FHAIN Altbau nahe Boxhagener Platz").id == "friedrichshain"
    assert detect_district("Neukölln Reuterkiez").id == "neukoelln"


def test_selected_districts():
    assert matches_selected("Kreuzberg Wrangelkiez", ["kreuzberg"])
    assert not matches_selected("Spandau Altstadt", ["kreuzberg", "neukoelln"])
    assert matches_selected("Berlin, genaue Lage auf Anfrage", ["kreuzberg"])

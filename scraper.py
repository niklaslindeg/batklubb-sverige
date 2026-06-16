"""
Scraper för svenska båtklubbar från Båtunionen och SSRS.
Kör: python scraper.py
Sparar resultat till data/clubs.json
"""

import json
import time
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; BatklubbSverige/1.0; research project)"
})

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = DATA_DIR / "clubs.json"


def scrape_batunionen() -> list[dict]:
    """Hämtar klubbar från Båtunionens klubbregister."""
    clubs = []
    print("Hämtar klubbar från Båtunionen...")

    # Båtunionen listar klubbar per distrikt via sitt sökformulär
    base_url = "https://www.batunionen.se/hitta-klubb/"

    try:
        resp = SESSION.get(base_url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Fel vid hämtning av Båtunionen: {e}")
        return clubs

    soup = BeautifulSoup(resp.text, "lxml")

    # Leta efter klubblänkar/kort på sidan
    # Båtunionens sida har klubbar listade i .member-list eller liknande
    entries = soup.select(".member-list-item, .club-card, article.club, .post-type-archive-club article")

    if not entries:
        # Fallback: leta efter alla länkade klubbnamn i listor
        entries = soup.select("ul.clubs li, .clubs-list li, .wpb_wrapper li")

    print(f"  Hittade {len(entries)} poster på sidan.")

    for entry in entries:
        name_el = entry.select_one("h2, h3, h4, .club-name, strong")
        link_el = entry.select_one("a[href]")

        name = name_el.get_text(strip=True) if name_el else (
            link_el.get_text(strip=True) if link_el else None
        )
        if not name:
            continue

        club: dict = {"name": name, "source": "batunionen"}

        if link_el:
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.batunionen.se" + href
            club["url"] = href

        # Adress/ort
        addr_el = entry.select_one(".address, .location, .city, p")
        if addr_el:
            club["address"] = addr_el.get_text(strip=True)

        clubs.append(club)

    return clubs


def scrape_ssrs() -> list[dict]:
    """Hämtar räddningssällskapets stationer (komplement)."""
    clubs = []
    print("Hämtar stationer från SSRS...")
    url = "https://www.ssrs.se/hitta-station/"
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Fel vid hämtning av SSRS: {e}")
        return clubs

    soup = BeautifulSoup(resp.text, "lxml")
    entries = soup.select(".station-list-item, .station-card, article")

    for entry in entries:
        name_el = entry.select_one("h2, h3, .station-name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        club: dict = {"name": name, "source": "ssrs"}
        addr_el = entry.select_one(".address, p")
        if addr_el:
            club["address"] = addr_el.get_text(strip=True)
        clubs.append(club)

    print(f"  Hittade {len(entries)} poster.")
    return clubs


def geocode_clubs(clubs: list[dict]) -> list[dict]:
    """
    Geokodning via Nominatim (OpenStreetMap) för klubbar som saknar koordinater.
    Max 1 req/sekund enligt användarvillkor.
    """
    geocoded = []
    needs_geo = [c for c in clubs if "lat" not in c and c.get("address")]
    print(f"\nGeokodning: {len(needs_geo)} av {len(clubs)} klubbar saknar koordinater...")

    nominatim = "https://nominatim.openstreetmap.org/search"

    for i, club in enumerate(clubs):
        if "lat" in club:
            geocoded.append(club)
            continue

        address = club.get("address") or club.get("name", "")
        query = f"{address}, Sverige"

        try:
            r = SESSION.get(nominatim, params={
                "q": query, "format": "json", "limit": 1, "countrycodes": "se"
            }, headers={"Accept-Language": "sv"}, timeout=10)
            results = r.json()
            if results:
                club["lat"] = float(results[0]["lat"])
                club["lon"] = float(results[0]["lon"])
                print(f"  [{i+1}/{len(clubs)}] OK: {club['name']}")
            else:
                print(f"  [{i+1}/{len(clubs)}] Ej hittad: {club['name']}")
        except Exception as e:
            print(f"  [{i+1}/{len(clubs)}] Fel: {club['name']} — {e}")

        geocoded.append(club)
        time.sleep(1.1)  # respektera Nominatim rate limit

    return geocoded


def load_fallback_data() -> list[dict]:
    """
    Grunddata med ~30 välkända svenska båtklubbar som fallback
    om scraping inte lyckas (t.ex. vid nätverksproblem).
    """
    return [
        {"name": "Kungliga Svenska Segel Sällskapet (KSSS)", "city": "Lidingö", "lat": 59.3667, "lon": 18.1333, "url": "https://www.ksss.se", "source": "fallback"},
        {"name": "Göteborgs Kungliga Segelsällskap (GKSS)", "city": "Göteborg", "lat": 57.6889, "lon": 11.8594, "url": "https://www.gkss.se", "source": "fallback"},
        {"name": "Stockholms Segelsällskap (SS)", "city": "Stockholm", "lat": 59.3254, "lon": 18.0700, "url": "https://www.stockholmssegelsallskap.se", "source": "fallback"},
        {"name": "Malmö Segelsällskap (MSS)", "city": "Malmö", "lat": 55.5780, "lon": 12.9920, "url": "https://www.malmosegelsallskap.se", "source": "fallback"},
        {"name": "Helsingborgs Segelsällskap", "city": "Helsingborg", "lat": 56.0465, "lon": 12.6945, "source": "fallback"},
        {"name": "Västerås Segelsällskap", "city": "Västerås", "lat": 59.6099, "lon": 16.5448, "source": "fallback"},
        {"name": "Uppsala Segelsällskap", "city": "Uppsala", "lat": 59.8586, "lon": 17.6389, "source": "fallback"},
        {"name": "Norrköpings Segelsällskap", "city": "Norrköping", "lat": 58.5877, "lon": 16.1924, "source": "fallback"},
        {"name": "Linköpings Segelsällskap", "city": "Linköping", "lat": 58.4108, "lon": 15.6214, "source": "fallback"},
        {"name": "Örebro Segelsällskap", "city": "Örebro", "lat": 59.2741, "lon": 15.2066, "source": "fallback"},
        {"name": "Sundsvalls Segelsällskap", "city": "Sundsvall", "lat": 62.3908, "lon": 17.3069, "source": "fallback"},
        {"name": "Umeå Segelsällskap", "city": "Umeå", "lat": 63.8258, "lon": 20.2630, "source": "fallback"},
        {"name": "Luleå Segelsällskap", "city": "Luleå", "lat": 65.5848, "lon": 22.1547, "source": "fallback"},
        {"name": "Kalmar Segelsällskap", "city": "Kalmar", "lat": 56.6616, "lon": 16.3557, "source": "fallback"},
        {"name": "Karlskrona Segelsällskap", "city": "Karlskrona", "lat": 56.1612, "lon": 15.5869, "source": "fallback"},
        {"name": "Visby Segelsällskap", "city": "Visby", "lat": 57.6348, "lon": 18.2948, "source": "fallback"},
        {"name": "Västervik Segelsällskap", "city": "Västervik", "lat": 57.7584, "lon": 16.6368, "source": "fallback"},
        {"name": "Oskarshamns Segelsällskap", "city": "Oskarshamn", "lat": 57.2648, "lon": 16.4480, "source": "fallback"},
        {"name": "Strömstad Segelsällskap", "city": "Strömstad", "lat": 58.9369, "lon": 11.1703, "source": "fallback"},
        {"name": "Lysekils Segelsällskap", "city": "Lysekil", "lat": 58.2752, "lon": 11.4357, "source": "fallback"},
        {"name": "Marstrand Segelsällskap", "city": "Marstrand", "lat": 57.8866, "lon": 11.5800, "source": "fallback"},
        {"name": "Grebbestads Segelsällskap", "city": "Grebbestad", "lat": 58.6933, "lon": 11.2508, "source": "fallback"},
        {"name": "Halmstads Segelsällskap", "city": "Halmstad", "lat": 56.6744, "lon": 12.8577, "source": "fallback"},
        {"name": "Varbergs Segelsällskap", "city": "Varberg", "lat": 57.1057, "lon": 12.2508, "source": "fallback"},
        {"name": "Falkenbergs Segelsällskap", "city": "Falkenberg", "lat": 56.9058, "lon": 12.4914, "source": "fallback"},
        {"name": "Vänersborgs Segelsällskap", "city": "Vänersborg", "lat": 58.3808, "lon": 12.3236, "source": "fallback"},
        {"name": "Trollhättans Segelsällskap", "city": "Trollhättan", "lat": 58.2838, "lon": 12.2886, "source": "fallback"},
        {"name": "Karlstads Segelsällskap", "city": "Karlstad", "lat": 59.3793, "lon": 13.5036, "source": "fallback"},
        {"name": "Gävle Segelsällskap", "city": "Gävle", "lat": 60.6749, "lon": 17.1413, "source": "fallback"},
        {"name": "Hudiksvalls Segelsällskap", "city": "Hudiksvall", "lat": 61.7283, "lon": 17.1044, "source": "fallback"},
    ]


def main():
    print("=== Båtklubb Sverige Scraper ===\n")

    all_clubs = []

    # Försök scrapa live-data
    bu_clubs = scrape_batunionen()
    all_clubs.extend(bu_clubs)

    # Om vi inte fick något, använd fallback-data
    if not all_clubs:
        print("\nIngen live-data hämtad — använder fallback-data.")
        all_clubs = load_fallback_data()
    else:
        # Geokoda klubbar som saknar koordinater
        all_clubs = geocode_clubs(all_clubs)

    # Ta bort dubbletter på namn
    seen = set()
    unique = []
    for c in all_clubs:
        key = c["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    print(f"\nTotalt {len(unique)} unika klubbar sparade.")
    OUTPUT_FILE.write_text(json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Data sparad till: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

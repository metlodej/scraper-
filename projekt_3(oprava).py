"""
projekt_3.py: třetí projekt

author: Metodej Vanka
email: metodejvanka@gmail.com
discord: NemamDiscord#1234
"""

import sys
import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ============================================================
# CONSTANTS
# ============================================================

# All links in the HTML are relative (e.g. "ps311?xjazyk=CZ&...").
# urljoin() combines this base with the relative path to make a full URL.
BASE_URL = "https://volby.cz/pls/ps2017nss/"

# We send these headers with every request so the server thinks
# we are a real browser. Without this it may return 403 Forbidden.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "cs,en-US;q=0.7,en;q=0.3",
}


# ============================================================
# HELPER: download a page and return parsed HTML
# ============================================================

def get_soup(url):
    """
    Downloads a webpage and returns a BeautifulSoup object.
    BeautifulSoup turns raw HTML into a searchable tree of objects.
    If anything goes wrong we print an error and exit.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"Chyba: Server vrátil kód {response.status_code} pro URL: {url}")
            if response.status_code == 571:
                print("Poznámka: Kód 571 je výpadek databáze na straně volby.cz.")
            sys.exit(1)
        return BeautifulSoup(response.text, "html.parser")
    except requests.exceptions.ConnectionError:
        print(f"Chyba: Nelze se připojit na URL: {url}")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"Chyba: Požadavek na {url} vypršel.")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování stránky: {e}")
        sys.exit(1)


# ============================================================
# STEP 1: get the list of municipalities from the district page
# ============================================================

def get_municipalities(district_url):
    """
    Reads the district overview page and returns a list of dicts:
        [{"code": "506761", "location": "Alojzov", "url": "https://..."}, ...]

    From the real HTML we confirmed:
    - Municipality rows have class="cislo" on the first <td>
    - The name is in the next <td class="overflow_name">
    - The link href is relative, e.g. "ps311?xjazyk=CZ&xkraj=12&xobec=506761&xvyber=7103"
    - Valid codes are exactly 6 digits
    """
    print(f"Stahuji seznam obcí z: {district_url}")
    soup = get_soup(district_url)

    municipalities = []

    for code_cell in soup.find_all("td", class_="cislo"):
        link_tag = code_cell.find("a")
        if not link_tag:
            continue

        code = code_cell.text.strip()

        # Only 6-digit codes are real municipality codes
        if not code.isdigit() or len(code) != 6:
            continue

        name_cell = code_cell.find_next_sibling("td", class_="overflow_name")
        if not name_cell:
            continue

        name = name_cell.text.strip()
        full_url = urljoin(BASE_URL, link_tag["href"])

        municipalities.append({
            "code":     code,
            "location": name,
            "url":      full_url,
        })

    if not municipalities:
        print("Chyba: Na zadané stránce nebyly nalezeny žádné obce.")
        sys.exit(1)

    print(f"Nalezeno {len(municipalities)} obcí.\n")
    return municipalities


# ============================================================
# STEP 2: scrape voting data from one municipality's detail page
# ============================================================

def scrape_municipality(url):
    """
    Downloads one municipality detail page and returns a dict with
    registered, envelopes, valid, and a parties sub-dict.

    --- Confirmed real HTML structure (from Alojzov page source) ---

    TURNOUT TABLE  id="ps311_t1"
    Has 3 rows: row[0] and row[1] are headers, row[2] is the data.
    All data cells have class="cislo". Columns (zero-indexed):
        [0] okrsky celkem
        [1] okrsky zpracovano
        [2] okrsky %
        [3] registered voters   ← we want this
        [4] envelopes issued     ← we want this
        [5] volební účast %
        [6] odevzdané obálky
        [7] valid votes          ← we want this
        [8] % platných hlasů

    PARTY TABLES  — two side-by-side tables with class="table"
    Each has headers with id="t1sa1"/"t2sa1" for Strana column.
    Each party row structure:
        <td class="cislo">     party number   (index 0)
        <td class="overflow_name">  party name     (index 1)
        <td class="cislo">     vote count     (index 2)
        <td class="cislo">     vote %         (index 3)
        <td ...>               přednostní     (index 4)

    We identify party tables by looking for a <th> with id starting
    with "t1sa1" or "t2sa1" — unique to the party result tables.
    """
    soup = get_soup(url)
    result = {}

    # --- Turnout numbers ---
    # The table has id="ps311_t1" — confirmed from real HTML
    turnout_table = soup.find("table", {"id": "ps311_t1"})
    if turnout_table:
        rows = turnout_table.find_all("tr")
        # row[0] = first header row, row[1] = second header row, row[2] = data
        if len(rows) >= 3:
            cells = rows[2].find_all("td")
            if len(cells) >= 8:
                # \xa0 is a non-breaking space used as thousands separator
                # e.g. "1 234" stored as "1\xa0234" → replace to get "1234"
                result["registered"] = cells[3].text.replace("\xa0", "").strip()
                result["envelopes"]  = cells[4].text.replace("\xa0", "").strip()
                result["valid"]      = cells[7].text.replace("\xa0", "").strip()

    result.setdefault("registered", "0")
    result.setdefault("envelopes",  "0")
    result.setdefault("valid",      "0")

    # --- Party votes ---
    parties = {}

    # Find the two party tables by their unique header th ids: t1sa1 and t2sa1
    for header_id in ["t1sa1", "t2sa1"]:
        th = soup.find("th", {"id": header_id})
        if not th:
            continue
        # .find_parent("table") walks up the HTML tree to get the table this <th> is inside
        table = th.find_parent("table")
        if not table:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all("td")

            # Valid party rows have at least 3 cells:
            # [0] number, [1] name (class overflow_name), [2] vote count
            if len(cells) < 3:
                continue

            # Skip filler rows — they have class="hidden_td" and text "-"
            if "hidden_td" in cells[0].get("class", []):
                continue

            party_name = cells[1].text.strip()
            vote_count = cells[2].text.replace("\xa0", "").strip()

            # Skip empty names and non-numeric vote counts (header/summary rows)
            if not party_name or party_name == "-":
                continue
            if not vote_count.isdigit():
                continue

            parties[party_name] = vote_count

    result["parties"] = parties
    return result


# ============================================================
# STEP 3: write everything to a CSV file
# ============================================================

def save_to_csv(all_rows, all_parties, output_file):
    """
    Writes the collected data to a CSV file.

    header = fixed columns + one column per party
    DictWriter matches dict keys to column names automatically.
    setdefault fills "0" for any party that didn't run in a given municipality.
    newline="" prevents blank lines on Windows.
    encoding="utf-8" keeps Czech characters correct.
    """
    header = ["code", "location", "registered", "envelopes", "valid"] + all_parties

    try:
        with open(output_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            writer.writeheader()
            for row in all_rows:
                for party in all_parties:
                    row.setdefault(party, "0")
                writer.writerow(row)
        print(f"\nHotovo! Data uložena do souboru: '{output_file}'")
    except IOError as e:
        print(f"Chyba: Nelze zapsat do souboru '{output_file}': {e}")
        sys.exit(1)


# ============================================================
# MAIN — argument validation + orchestration
# ============================================================

def main():
    """
    sys.argv[0] = script name, sys.argv[1] = URL, sys.argv[2] = output file.
    We validate both arguments before doing anything.
    """
    if len(sys.argv) != 3:
        print("Chyba: Skript vyžaduje právě 2 argumenty.")
        print("Použití:  python projekt_3.py <URL> <vystupni_soubor.csv>")
        print('Příklad:  python projekt_3.py "https://volby.cz/pls/ps2017nss/ps32?xjazyk=CZ&xkraj=12&xnumnuts=7103" vysledky.csv')
        sys.exit(1)

    district_url = sys.argv[1]
    output_file  = sys.argv[2]

    if "volby.cz" not in district_url:
        print("Chyba: Odkaz musí pocházet z domény volby.cz.")
        sys.exit(1)

    if "ps32" not in district_url:
        print("Chyba: Odkaz musí vést na přehled okresu (URL musí obsahovat 'ps32').")
        sys.exit(1)

    if not output_file.endswith(".csv"):
        print("Chyba: Výstupní soubor musí mít příponu .csv")
        sys.exit(1)

    # Step 1 — get all municipalities
    municipalities = get_municipalities(district_url)

    # Step 2 — scrape each one
    all_rows    = []
    all_parties = []

    for mun in municipalities:
        print(f"  Stahuji: {mun['location']} ({mun['code']})")
        data = scrape_municipality(mun["url"])

        row = {
            "code":       mun["code"],
            "location":   mun["location"],
            "registered": data["registered"],
            "envelopes":  data["envelopes"],
            "valid":      data["valid"],
        }

        for party_name, votes in data["parties"].items():
            row[party_name] = votes
            if party_name not in all_parties:
                all_parties.append(party_name)

        all_rows.append(row)

    # Step 3 — save to CSV
    save_to_csv(all_rows, all_parties, output_file)


if __name__ == "__main__":
    main()

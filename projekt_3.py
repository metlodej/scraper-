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


def ziskej_soup(url):
    """Stáhne stránku s maskovanou hlavičkou, aby server nehlásil chybu 571."""
    hlavicky = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "cs,en-US;q=0.7,en;q=0.3"
    }
    try:
        odpoved = requests.get(url, headers=hlavicky)
        if odpoved.status_code == 200:
            return BeautifulSoup(odpoved.text, "html.parser")
        else:
            print(f"Chyba: Nepodařilo se načíst stránku. Status kód: {odpoved.status_code}")
            print("Poznámka: Pokud vidíte kód 571, web volby.cz má zrovna výpadek databáze.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Chyba při požadavku na URL: {e}")
        sys.exit(1)


def zpracuj_obec(url_obce):
    """Vytáhne data o voličích, obálkách a hlasech stran z detailu obce."""
    soup = ziskej_soup(url_obce)
    data_obce = {}


    tabulka_info = soup.find("table", {"id": "ps311_t1"})
    if not tabulka_info:
     
        tabulka_info = soup.find("table")

    if tabulka_info:
        radky = tabulka_info.find_all("tr")
        if len(radky) >= 3:
            bunky = radky[2].find_all("td")
            if len(bunky) >= 8:
                data_obce["registered"] = bunky[3].text.replace("\xa0", "").strip()
                data_obce["envelopes"] = bunky[4].text.replace("\xa0", "").strip()
                data_obce["valid"] = bunky[7].text.replace("\xa0", "").strip()

    data_obce.setdefault("registered", "0")
    data_obce.setdefault("envelopes", "0")
    data_obce.setdefault("valid", "0")

    strany_hlasy = {}
    for tab_id in ["t1sa1", "t2sa1"]:
        tabulka_stran = soup.find("table", {"id": f"ps311_{tab_id}"})
        if tabulka_stran:
            radky = tabulka_stran.find_all("tr")
            for radek in radky:
                bunky = radek.find_all("td")
                if len(bunky) >= 3:
                    nazev_strany = bunky[1].text.strip()
                    if nazev_strany and nazev_strany != "-":
                        hlasy = bunky[2].text.replace("\xa0", "").strip()
                        strany_hlasy[nazev_strany] = hlasy

    data_obce["strany"] = strany_hlasy
    return data_obce


def main():
    # Ověření argumentů příkazové řádky
    if len(sys.argv) != 3:
        print("Chyba: Nesprávný počet argumentů!")
        print("Použití: python projekt_3.py <URL_ODKAZ> <NAZEV_SOUBORU.csv>")
        sys.exit(1)

    hlavni_url = sys.argv[1]
    vystupni_soubor = sys.argv[2]

    if "volby.cz" not in hlavni_url:
        print("Chyba: Odkaz musí pocházet z domény volby.cz.")
        sys.exit(1)

    print(f"Navazuji spojení s webem volby.cz...")
    soup = ziskej_soup(hlavni_url)

    # Najdeme všechny řádky s obcemi na hlavní stránce okresu
    # Tabulky s obcemi mají ID ps311_t1sa1, ps311_t2sa1 atd.
    radky_obci = []
    for i in range(1, 4):
        tabulka = soup.find("table", {"id": f"ps311_t{i}sa1"})
        if tabulka:
            radky_obci.extend(tabulka.find_all("tr"))

    # Pokud by tabulky neměly ID, zkusíme najít všechny řádky v dokumentu obecně
    if not radky_obci:
        radky_obci = soup.find_all("tr")

    seznam_vsech_obci = []
    vsechny_strany = []

    print("Stahuji a zpracovávám data pro jednotlivé obce...")

    for radek in radky_obci:
        bunky = radek.find_all("td")
        # Obec poznáme tak, že první buňka obsahuje kód (odkaz) a druhá název obce
        if len(bunky) >= 2 and bunky[0].find("a"):
            kod_obce = bunky[0].text.strip()
            nazev_obce = bunky[1].text.strip()
            
            # Kontrola, zda jde o validní šestimístný kód obce
            if not kod_obce.isdigit():
                continue

            odkaz_href = bunky[0].find("a")["href"]
            url_detail_obce = f"https://volby.cz/pls/ps2017nps/{odkaz_href}"

            print(f" -> {nazev_obce} ({kod_obce})")
            detaily = zpracuj_obec(url_detail_obce)

            radek_data = {
                "code": kod_obce,
                "location": nazev_obce,
                "registered": detaily["registered"],
                "envelopes": detaily["envelopes"],
                "valid": detaily["valid"]
            }
            radek_data.update(detaily["strany"])
            seznam_vsech_obci.append(radek_data)

            for strana in detaily["strany"].keys():
                if strana not in vsechny_strany:
                    vsechny_strany.append(strana)

    if not seznam_vsech_obci:
        print("Chyba: Na zadaném odkazu nebyly nalezeny žádné obce ke stažení.")
        sys.exit(1)

    # Definice výsledné hlavičky CSV podle image_0c91c8.png
    hlavicka = ["code", "location", "registered", "envelopes", "valid"] + vsechny_strany

    # Zápis dat do výsledného souboru
    try:
        with open(vystupni_soubor, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=hlavicka)
            writer.writeheader()
            for obec in seznam_vsech_obci:
                for strana in vsechny_strany:
                    if strana not in obec:
                        obec[strana] = "0"
                writer.writerow(obec)
        print(f"\n🎉 Hotovo! Data byla úspěšně exportována do: '{vystupni_soubor}'")
    except IOError as e:
        print(f"Chyba při zápisu do CSV souboru: {e}")


if __name__ == "__main__":
    main()
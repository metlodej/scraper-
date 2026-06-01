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
    """Pomocná funkce pro stažení stránky a vytvoření BeautifulSoup objektu."""
    # Přidána hlavička běžného prohlížeče, aby web volby.cz neblokoval skript chybou 571
    hlavicky = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        odpoved = requests.get(url, headers=hlavicky)
        if odpoved.status_code == 200:
            return BeautifulSoup(odpoved.text, "html.parser")
        else:
            print(f"Chyba: Nepodařilo se načíst stránku (Status kód: {odpoved.status_code})")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Chyba při požadavku na URL: {e}")
        sys.exit(1)


def zpracuj_obec(url_obce):
    """Navštíví detail obce a vytáhne informace o voličích, obálkách a hlasech stran."""
    soup = ziskej_soup(url_obce)
    data_obce = {}

    # 1. Registrovaní voliči, obálky a platné hlasy (tabulka s id="ps311_t1")
    tabulka_info = soup.find("table", {"id": "ps311_t1"})
    if tabulka_info:
        radek = tabulka_info.find_all("tr")[2]  # Třetí řádek obsahuje data
        bunky = radek.find_all("td")
        # Odstranění nezlomitelných mezer (\xa0) z čísel
        data_obce["registered"] = bunky[3].text.replace("\xa0", "").strip()
        data_obce["envelopes"] = bunky[4].text.replace("\xa0", "").strip()
        data_obce["valid"] = bunky[7].text.replace("\xa0", "").strip()

    # 2. Hlasy pro jednotlivé politické strany (tabulky t1sa1 a t2sa1)
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
    # Kontrola správného počtu argumentů podle bodu 4 a 5 zadání
    if len(sys.argv) != 3:
        print("Chyba: Nesprávný počet argumentů!")
        print("Použití: python projekt_3.py <URL_UZEMNIHO_CELKU> <NAZEV_VYSTUPU.csv>")
        sys.exit(1)

    hlavni_url = sys.argv[1]
    vystupni_soubor = sys.argv[2]

    # Základní ověření správnosti odkazu
    if "volby.cz" not in hlavni_url:
        print("Chyba: První argument musí obsahovat platný odkaz z webu volby.cz.")
        sys.exit(1)

    print(f"Spouštím scrapování pro odkaz: {hlavni_url}")
    soup = ziskej_soup(hlavni_url)

    # Najdeme všechny řádky s obcemi na hlavní stránce okresu
    radky_obci = []
    for i in range(1, 4):
        tabulka = soup.find("table", {"id": f"ps311_t{i}sa1"})
        if tabulka:
            radky_obci.extend(tabulka.find_all("tr"))

    seznam_vsech_obci = []
    vsechny_strany = []

    print("Načítám seznam obcí a stahuji podrobná data...")

    # Procházíme řádky a filtrujeme ty, které obsahují data o obcích
    for radek in radky_obci:
        bunky = radek.find_all("td")
        if len(bunky) >= 3 and bunky[0].find("a"):
            kod_obce = bunky[0].text.strip()
            nazev_obce = bunky[1].text.strip()
            
            # Vytvoření absolutní URL adresy pro detail obce
            odkaz_href = bunky[0].find("a")["href"]
            url_detail_obce = f"https://volby.cz/pls/ps2017nps/{odkaz_href}"

            # Stažení detailních dat o obci
            print(f"Zpracovávám obec: {nazev_obce} ({kod_obce})")
            detaily = zpracuj_obec(url_detail_obce)

            # Sloučení základních údajů s detaily
            radek_data = {
                "code": kod_obce,
                "location": nazev_obce,
                "registered": detaily["registered"],
                "envelopes": detaily["envelopes"],
                "valid": detaily["valid"]
            }
            # Přidání hlasů pro strany
            radek_data.update(detaily["strany"])
            seznam_vsech_obci.append(radek_data)

            # Průběžně ukládáme názvy stran pro záhlaví
            for strana in detaily["strany"].keys():
                if strana not in vsechny_strany:
                    vsechny_strany.append(strana)

    # Definice záhlaví CSV souboru přesně podle zadání
    hlavicka = ["code", "location", "registered", "envelopes", "valid"] + vsechny_strany

    # Zápis dat do CSV souboru
    try:
        with open(vystupni_soubor, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=hlavicka)
            writer.writeheader()
            for obec in seznam_vsech_obci:
                # Pokud v nějaké obci strana nekandidovala, vyplníme 0
                for strana in vsechny_strany:
                    if strana not in obec:
                        obec[strana] = "0"
                writer.writerow(obec)
        print(f"\nHotovo! Výsledky byly úspěšně uloženy do souboru '{vystupni_soubor}'.")
    except IOError as e:
        print(f"Chyba při zápisu do CSV souboru: {e}")


if __name__ == "__main__":
    main()
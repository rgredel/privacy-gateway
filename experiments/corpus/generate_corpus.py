"""
generate_corpus.py – Generator korpusu testowego dla eksperymentów badawczych.

Parsuje fake_data.xml, dodaje syntetyczne dane, tworzy ~20 dokumentów
w formie tekstu naturalnego (NIE ustrukturyzowanego XML/JSON).
Uwzględnia polską fleksję oraz przypadki testowe False Positive.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Ścieżki ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
XML_PATH = PROJECT_ROOT / "fake_data.xml"
OUTPUT_PATH = SCRIPT_DIR / "corpus.json"

# ══════════════════════════════════════════════════════════════════════════════
# 1. Ekstrakcja danych PII z fake_data.xml
# ══════════════════════════════════════════════════════════════════════════════

def parse_xml_entities(xml_path: Path) -> list[dict]:
    """Parsuje XML i zwraca listę słowników z danymi PII per faktura."""
    raw = xml_path.read_text(encoding="utf-8")
    wrapped = f"<wrapper>{raw}</wrapper>"
    tree = ET.fromstring(wrapped)

    records = []
    for root_elem in tree.findall("root"):
        rec = {}
        # Nagłówek
        header = root_elem.find("naglowek")
        if header is not None:
            rec["numer_faktury"] = (header.findtext("numer_faktury") or "").strip()
            rec["data_wystawienia"] = (header.findtext("data_wystawienia") or "").strip()
            rec["miejsce_wystawienia"] = (header.findtext("miejsce_wystawienia") or "").strip()

        # Kontrahent
        kontr = root_elem.find("kontrahent")
        if kontr is not None:
            rec["nazwa_firmy"] = (kontr.findtext("nazwa") or "").strip()
            rec["nip"] = (kontr.findtext("nip") or "").strip()
            rec["regon"] = (kontr.findtext("regon") or "").strip()
            
            # Osoba kontaktowa + prosta fleksja
            osoba = (kontr.findtext("osoba_kontaktowa") or "").strip()
            rec["osoba_kontaktowa"] = osoba
            if "Anna Nowak-Zielińska" in osoba:
                rec["osoba_kontaktowa_gen"] = "Anny Nowak-Zielińskiej"
            elif "Marek Kwiatkowski" in osoba:
                rec["osoba_kontaktowa_gen"] = "Marka Kwiatkowskiego"
            else:
                rec["osoba_kontaktowa_gen"] = osoba

            adres = kontr.find("adres")
            if adres is not None:
                rec["ulica"] = (adres.findtext("ulica") or "").strip()
                rec["kod_pocztowy"] = (adres.findtext("kod_pocztowy") or "").strip()
                rec["miasto"] = (adres.findtext("miasto") or "").strip()

        # Płatność
        plat = root_elem.find("platnosc")
        if plat is not None:
            rec["rachunek_bankowy"] = (plat.findtext("rachunek_bankowy") or "").strip()
            rec["kwota_brutto"] = (plat.findtext("kwota_brutto") or "").strip()

        records.append(rec)
    return records

# ══════════════════════════════════════════════════════════════════════════════
# 2. Dodatkowe dane syntetyczne (rozszerzające korpus)
# ══════════════════════════════════════════════════════════════════════════════

SYNTHETIC_ENTITIES = [
    {
        "nazwa_firmy": 'Biuro Rachunkowe "Cyfra" Sp. z o.o.',
        "nip": "7891234560",
        "regon": "987654321",
        "osoba_kontaktowa": "Katarzyna Dąbrowska",
        "osoba_kontaktowa_gen": "Katarzyny Dąbrowskiej",
        "ulica": "ul. Krakowska 45",
        "kod_pocztowy": "31-066",
        "miasto": "Kraków",
        "rachunek_bankowy": "PL83109010140000071219812874",
        "numer_faktury": "FV/2026/00087",
        "pesel": "90010112345",
    },
    {
        "nazwa_firmy": "Usługi Transportowe Kowalski",
        "nip": "6340127890",
        "regon": "321654987",
        "osoba_kontaktowa": "Jan Kowalski",
        "osoba_kontaktowa_gen": "Jana Kowalskiego",
        "ulica": "ul. Długa 7/3",
        "kod_pocztowy": "80-827",
        "miasto": "Gdańsk",
        "rachunek_bankowy": "PL27114020040000300201355387",
        "numer_faktury": "FV/2026/00122",
        "pesel": "85072309876",
    },
    {
        "nazwa_firmy": "Kancelaria Podatkowa Wiśniewski i Wspólnicy",
        "nip": "1132567890",
        "osoba_kontaktowa": "Tomasz Wiśniewski",
        "osoba_kontaktowa_gen": "Tomasza Wiśniewskiego",
        "ulica": "ul. Nowy Świat 22/10",
        "kod_pocztowy": "00-373",
        "miasto": "Warszawa",
        "rachunek_bankowy": "PL50102011560000710204117893",
        "numer_faktury": "FV/2026/00201",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# 3. Szablony dokumentów naturalnych
# ══════════════════════════════════════════════════════════════════════════════

def generate_documents(xml_records: list[dict], synth: list[dict]) -> list[dict]:
    corpus = []
    doc_id = 0
    e = xml_records[0]
    e2 = synth[0]
    e3 = synth[2]
    e4 = synth[1]

    # ── KATEGORIA: Proste ─────────────────────────────────────────────────────
    
    corpus.append({
        "doc_id": doc_id,
        "text": f'Właścicielem firmy jest {e["osoba_kontaktowa"]} o numerze NIP {e["nip"]}.',
        "pii": [e["osoba_kontaktowa"], e["nip"]],
        "category": "simple"
    })
    doc_id += 1

    corpus.append({
        "doc_id": doc_id,
        "text": f'Wiadomość dotyczy {e["osoba_kontaktowa_gen"]} w sprawie zaległych składek.',
        "pii": [e["osoba_kontaktowa_gen"]],
        "category": "simple"
    })
    doc_id += 1

    corpus.append({
        "doc_id": doc_id,
        "text": f'Osobą kontaktową w biurze jest {e2["osoba_kontaktowa"]}.',
        "pii": [e2["osoba_kontaktowa"]],
        "category": "simple"
    })
    doc_id += 1

    # ── KATEGORIA: Średnie ────────────────────────────────────────────────────

    corpus.append({
        "doc_id": doc_id,
        "text": f'Proszę o wysłanie faktury dla {e2["osoba_kontaktowa_gen"]} na adres w {e2["miasto"]}.',
        "pii": [e2["osoba_kontaktowa_gen"], e2["miasto"]],
        "category": "medium"
    })
    doc_id += 1

    corpus.append({
        "doc_id": doc_id,
        "text": f'Kontakt w sprawie płatności: {e4["osoba_kontaktowa"]}, NIP {e4["nip"]}.',
        "pii": [e4["osoba_kontaktowa"], e4["nip"]],
        "category": "medium"
    })
    doc_id += 1

    # ── KATEGORIA: Złożone ────────────────────────────────────────────────────

    corpus.append({
        "doc_id": doc_id,
        "text": (
            f'Informuję, że pan {e4["osoba_kontaktowa"]} z firmy {e4["nazwa_firmy"]} '
            f'zmienił numer konta na {e4["rachunek_bankowy"]}. Proszę zaktualizować '
            f'kartotekę {e4["osoba_kontaktowa_gen"]} w systemie RAG.'
        ),
        "pii": [e4["osoba_kontaktowa"], e4["nazwa_firmy"], e4["rachunek_bankowy"], e4["osoba_kontaktowa_gen"]],
        "category": "complex"
    })
    doc_id += 1

    corpus.append({
        "doc_id": doc_id,
        "text": (
            f'Zgodnie z umową, {e3["osoba_kontaktowa"]} (firma {e3["nazwa_firmy"]}, NIP {e3["nip"]}) '
            f'wystawi fakturę dla {e["osoba_kontaktowa_gen"]} na kwotę brutto {e["kwota_brutto"]}.'
        ),
        "pii": [e3["osoba_kontaktowa"], e3["nazwa_firmy"], e3["nip"], e["osoba_kontaktowa_gen"]],
        "category": "complex"
    })
    doc_id += 1

    # ── KATEGORIA: False Positive Bait (Dane publiczne / znane) ────────────────

    corpus.append({
        "doc_id": doc_id,
        "text": "Wybitny astronom Mikołaj Kopernik urodził się w Toruniu i wstrzymał słońce.",
        "pii": [],
        "category": "false_positive_bait"
    })
    doc_id += 1

    corpus.append({
        "doc_id": doc_id,
        "text": "Oficjalny adres Sejmu to ul. Wiejska 4, 00-902 Warszawa. Proszę tam nic nie wysyłać.",
        "pii": [],
        "category": "false_positive_bait"
    })
    doc_id += 1

    corpus.append({
        "doc_id": doc_id,
        "text": "Wzór numeru NIP dla konta testowego to 000-000-00-00 lub 1234567890.",
        "pii": [],
        "category": "false_positive_bait"
    })
    doc_id += 1

    corpus.append({
        "doc_id": doc_id,
        "text": "Maria Skłodowska-Curie odkryła rad i polon, pracując w Paryżu.",
        "pii": [],
        "category": "false_positive_bait"
    })
    doc_id += 1

    # ── KATEGORIA: Czyste dokumenty ───────────────────────────────────────────

    corpus.append({
        "doc_id": doc_id,
        "text": "Proszę o przygotowanie raportu sprzedaży za zeszły miesiąc.",
        "pii": [],
        "category": "clean"
    })
    doc_id += 1

    return corpus

# ══════════════════════════════════════════════════════════════════════════════
# 4. Uruchomienie
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"[CORPUS] Parsowanie XML: {XML_PATH}")
    xml_records = parse_xml_entities(XML_PATH)
    
    print("[CORPUS] Generowanie dokumentów...")
    corpus = generate_documents(xml_records, SYNTHETIC_ENTITIES)
    
    # Statystyki
    total_pii = sum(len(d["pii"]) for d in corpus)
    print(f"  => Wygenerowano {len(corpus)} dokumentów, łącznie {total_pii} encji PII.")

    # Zapis
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    print(f"[CORPUS] Zapisano => {OUTPUT_PATH}")

if __name__ == "__main__":
    main()

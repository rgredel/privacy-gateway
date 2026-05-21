import json
import asyncio
from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI
from src.app.core.config import settings

# Konfiguracja
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_FILE = PROJECT_ROOT / "experiments/corpus/fp_test_corpus.json"
NUM_DOCS = 50

PROMPT = """
Wygeneruj 50 krótkich tekstów w języku polskim (każdy 2-4 zdania), które zawierają dane przypominające dane osobowe (imiona, nazwiska, adresy, NIP), ale są one WIEDZĄ POWSZECHNĄ, POSTACIAMI HISTORYCZNYMI lub ADRESAMI PUBLICZNYMI, których NIE NALEŻY anonimizować.

Przykłady tego, co ma być w tekstach:
1. Postacie historyczne (np. Fryderyk Chopin, Mikołaj Kopernik).
2. Adresy urzędów i zabytków (np. ul. Wiejska 4 w Warszawie, Wawel 5 w Krakowie).
3. Przykładowe dane z instrukcji (np. 'Wpisz Jan Kowalski w polu imię').
4. Nazwy dużych firm publicznych (np. PKN Orlen, KGHM).
5. Nazwy świąt i wydarzeń (np. Dzień Niepodległości).

Zwróć wynik jako listę JSON, gdzie każdy element to:
{
  "doc_id": numer,
  "text": "treść tekstu",
  "entities": []
}
Ważne: Pole 'entities' musi być zawsze pustą listą, ponieważ te dane NIE SĄ PII w kontekście prywatności.
"""

async def generate_fp_corpus():
    print(f"Generowanie {NUM_DOCS} dokumentów testowych FP...")
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key
    )
    
    response = await llm.ainvoke(PROMPT)
    
    # Wyciąganie JSON z odpowiedzi
    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    
    try:
        data = json.loads(content)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Sukces! Korpus zapisany w: {OUTPUT_FILE}")
    except Exception as e:
        print(f"Błąd parsowania: {e}")
        print("Surowa treść:")
        print(content)

if __name__ == "__main__":
    asyncio.run(generate_fp_corpus())

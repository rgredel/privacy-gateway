# Privacy Gateway 🛡️

System wieloagentowy (Multi-Agent System) oparty na **LangGraph**, służący do bezpiecznego przetwarzania danych wrażliwych (PII) przed wysłaniem ich do chmurowych modeli LLM.

## 🚀 Główne Funkcje
- **Hybrydowa Detekcja PII**: Połączenie silnika Microsoft Presidio (wzorce) z lokalnym modelem LLM (kontekst).
- **Lokalne Przetwarzanie**: Wykorzystanie modelu **Bielik v3** (via Ollama) do anonimizacji, co gwarantuje, że surowe dane nie opuszczają lokalnej infrastruktury.
- **Dynamiczne Maskowanie**: Automatyczna zamiana danych wrażliwych na bezpieczne tokeny i ich przywracanie po uzyskaniu odpowiedzi z chmury.
- **Guardrail Agent**: Weryfikacja zapytań pod kątem ataków typu Prompt Injection.

---

## 🛠️ Instalacja i Konfiguracja

### 1. Wymagania systemowe
- **Python**: 3.12.x
- **Ollama**: Do uruchomienia lokalnego modelu LLM.

### 2. Przygotowanie środowiska
```bash
# Stwórz wirtualne środowisko
python -m venv .venv

# Aktywuj środowisko (Windows)
.venv\Scripts\activate

# Zainstaluj zależności
pip install -r requirements.txt

# Pobierz model języka polskiego dla spaCy (wymagane dla Presidio)
python -m spacy download pl_core_news_lg
```

### 3. Konfiguracja Ollama (Model Bielik)
System wykorzystuje model **Bielik v3** zoptymalizowany pod język polski.
1. Pobierz i zainstaluj Ollama z [ollama.com](https://ollama.com).
2. Uruchom terminal i pobierz wymagany model:
```bash
ollama pull qooba/bielik-1.5b-v3.0-instruct:Q8_0
```

### 4. Zmienne środowiskowe (.env)
Stwórz plik `.env` w głównym katalogu projektu i uzupełnij go o swój klucz Google API (dla modelu Gemini):
```env
GOOGLE_API_KEY=twoj_klucz_tutaj
LANGSMITH_TRACING=true
LANGCHAIN_PROJECT=privacy-gateway
```

---

## 🏃 Uruchamianie

Projekt oferuje dwie główne metody interakcji:

### A. Interfejs Użytkownika (Chainlit)
Najwygodniejszy sposób na testowanie systemu w przeglądarce.
- Kliknij dwukrotnie w plik: `Uruchom_UI.bat`
- LUB uruchom komendą: `chainlit run app.py`

### B. LangGraph Studio
Do debugowania grafu i podglądu pracy agentów w czasie rzeczywistym.
- Kliknij dwukrotnie w plik: `Uruchom_Studio.bat`
- LUB uruchom komendą: `langgraph dev`

---

## 📊 Eksperymenty i Wyniki
W katalogu `experiments/` znajdują się skrypty pozwalające na replikację badań opisanych w pracy:
- `e1_pii_detection.py`: Skuteczność detekcji (F1-score).
- `e2_utility_score.py`: Analiza użyteczności danych po maskowaniu.
- `e3_prompt_injection.py`: Testy odporności na ataki.
- `e4_latency_benchmark.py`: Pomiary wydajności.

Wyniki są zapisywane automatycznie w folderze `experiments/results/`.

---
*Autor: Radosław*

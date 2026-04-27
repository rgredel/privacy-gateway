# Optymalizacja modułu detekcji PII (Zrównoleglenie i Fragmentacja)

## 1. Opis Problemu

Obecna implementacja Agenta Detekcji PII (`agents/detection.py`) działa w trybie sekwencyjnym, przekazując w całości pełny objętościowo zrzut danych (XML) z programu księgowego (np. Comarch ERP Optima) do małego, lokalnego modelu LLM klasy 1.5B (Bielik/Ollama).

**Skutki takiego podejścia:**
1. **Dławienie przeliczeniowe (Zbyt długi czas działania)**: Model walczy z przeanalizowaniem olbrzymiej paczki na jednym wątku logicznym. Skutkuje to ogromnym spowolnieniem czasu inferencji (Token-per-Second).
2. **Lost in the Middle (Zjawisko utraty kontekstu)**: Małe modele o limitowanym oknie kontekstowym mają tendencję do perfekcyjnego wyłapywania detali na początku i końcu promptu, totalnie "zapominając" logicznie przeanalizować zawartość ze środka wielkiej paczki tekstu.
3. **Pomięcia Detekcji PII**: Przeładowanie danymi powoduje, że model myli się i częściowo "nie zamaskowuje" wszystkich niezbędnych zmiennych (pomija NIP-y, nazwiska, czy adresy ze środka XML-a).

## 2. Propozycja Rozwiązania (Wzorzec Map-Reduce)

Aby zredukować dławienie i poprawić bystrość detekcji małego modelu, docelowo zaimplementowany zostanie architektoniczny wzorzec sztucznej inteligencji **Map-Reduce**, przenoszący obciążenie z pamięci głębokiej na zrównolegloną masową asynchroniczność.

### Architektura zmiany
1. **Rozbicie Tekstu (Chunking)**: 
   Użycie systemowego modułu `RecursiveCharacterTextSplitter` oferowanego przez *LangChain*.
   Potnie on wielki dokument wyeksportowany z *Optima* na małe logiczne porcje np. po `1500` znaków i z zakładką (Overlap) ustaloną na `150` znaków. Margines zakładkowy (Overlap) uchroni model przed gubieniem wartości – w razie przecięcia nazwiska w pół wyrazu, ten sam wyraz znajdzie się w obu oknach sąsiednich, gwarantując ciągłość kontekstu.
   
2. **Masowe Wywołanie Równoległe (Batching/Async)**:
   Zamiana starszego wariantu `chain.invoke()` na błyskawiczne **`chain.batch()`** w LangChain. Metoda `batch()` wewnętrznie wykorzystuje wielowątkową asynchroniczność (np. ThreadPoolExecutor). Podzielone np. na 10 paczek fragmenty zostaną wystrzelone do narzędzia LLM symultanicznie, by lokalny silnik Ollamy mógł analizować odizolowane problemy jednocześnie.
   Należy dodatkowo zastosować `return_exceptions=True`, co sprawia, że potknięcie modelu w badaniu jednej abstrakcyjnej paczki tekstu, nigdy nie wyrzuci globalnego "Exceptions", a zignoruje awarię i poprawnie poskłada części pochodzące z innych paczek.

3. **Agregacja Set (Reduce Phase)**:
   Pętla spinająca otrzymane odpowiedzi od małych zrównoleglonych pętli. Wszystkie wyłapane rekordy PII wrzucać będziemy do jednego strukturalnego obiektu `Set(List)` lub pętli, aby naturalnie i bezproblemowo usunąć powielone z racji zastosowania Overlap'u detekcje.

## 3. Szkic Implementacji (Kod docelowy dla detection.py)

Koncepcyjny kod na przyszłą przebudowę logiki agenta PII, nie do uruchomienia bezpośrednio, lecz jako wyznacznik architektury:

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter
# W agent logic:
text_to_analyze = state["raw_xml"]

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)
chunks = text_splitter.split_text(text_to_analyze)

# Wygenerowanie dynamicznej kolekcji zapytań dla paczki Batch
payload_list = [{"text": chunk} for chunk in chunks]

# Błyskawiczne RÓWNOLEGŁE wstrzyknięcie z return_exceptions w celu ucieczki z niekompatybilnych kawałków
results = chain.batch(payload_list, return_exceptions=True)

# Proces Agregacji Setu (Reducer)
aggregated_pii = set()
for res in results:
    if isinstance(res, Exception):
        # pomijamy felerną ramkę informując dev środowisko
        continue
    if res and res.detected_strings:
        for pii_entry in res.detected_strings:
            if pii_entry.strip():
                aggregated_pii.add(pii_entry.strip())

return {**state, "detected_pii": list(aggregated_pii)}
```

**Rozwiązanie to wyeliminuje nieefektywne przeciążenie i przywróci model Bielik na tory chirurgicznej precyzji działania.**

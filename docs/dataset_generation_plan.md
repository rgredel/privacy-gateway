# Plan generowania syntetycznego zbioru testowego (Benchmark)

## 1. Definicja problemu
W związku z koniecznością zachowania poufności (wymogi RODO/UODO) współpracujące biuro rachunkowe nie może udostępnić w pełni zaanotowanego korpusu rzeczywistych dokumentów finansowych. Z drugiej strony, ewaluacja Hybrydowego systemu Privacy Gateway (HerBERT + sędzia LLM) wymaga rygorystycznego, ustandaryzowanego zbioru danych, aby sprawdzić skuteczność, wydajność (E4) oraz odporność na ataki typu prompt injection (E3).

Ponieważ w architekturze wykorzystywane są pre-trenowane modele językowe w trybie *zero-shot* lub *few-shot*, **odrzucono konieczność budowy korpusu treningowego** do operacji *fine-tuningu*. Głównym celem jest stworzenie wysokiej jakości dedykowanego zbioru testowego (benchmarkowego), na którym system zostanie finalnie oceniony, a jego jakość potwierdzi ręczna weryfikacja przez ekspertów.

---

## 2. Założenia zbioru testowego
Zgodnie ze zaktualizowanym scenariuszem (brak treningu modelu):
*   **Wielkość zbioru:** 300 dokumentów.
*   **Szacowana objętość:** Około 50 000 tokenów.
*   **Przeznaczenie:** Wyłącznie ewaluacja i pomiary (E1, E2, E3, E4).
*   **Weryfikacja (Golden Standard):** Ograniczona liczba dokumentów pozwoli na szybką, ale dokładną ręczną weryfikację przez 2 niezależnych adnotatorów, co jest wymagane dla rzetelności prac badawczych.

---

## 3. Typy dokumentów i ich rozkład
Aby zbiór symulował prawdziwy ruch w biurze księgowym, musi charakteryzować się dużą różnorodnością strukturalną i językową. Korpus (300 sztuk) zostanie podzielony na cztery kategorie:

| Typ Dokumentu | Proporcja | Liczba | Średnia długość (tokeny) | Charakterystyka danych wrażliwych (PII) |
| :--- | :---: | :---: | :---: | :--- |
| **Transkrypcje systemów OCR** (faktury, paragony) | ~40% | 120 | Krótkie / Średnie (50–150) | Zwarte dane, dużo tagów `NIP`, `REGON`, `MISC_FIN` (kwoty), `ORG`. Tekst liniowy, mało pełnych zdań. |
| **Wyciągi i potwierdzenia przelewów** | ~25% | 75 | Krótkie (30–100) | Schematyczne teksty (tytuły przelewów), numery `ACCT` (IBAN), daty (`DATE`), nazwiska nadawców (`PER`). |
| **Umowy cywilnoprawne** (B2B, o dzieło, NDA) | ~20% | 60 | Długie (500–1500) | Sformalizowany, prawniczy język. PII skumulowane silnie w preambule (`PESEL`, numery dowodów, adresy `LOC`). |
| **Wewnętrzna korespondencja** (maile do biura) | ~15% | 45 | Średnie (100–300) | Chaotyczny tekst, nierzadko błędy językowe. PII wplecione bardzo naturalnie (np. *„Pani Kasiu, nowy NIP klienta to..."*). |

---

## 4. Metodologia techniczna (Jak to wygenerować?)
Samo poleganie na bibliotece `Faker` skutkuje nienaturalną, powtarzalną strukturą. Model LLM w roli sędziego bardzo szybko "nauczy się" takich szablonów i eksperyment nie wykaże jego zdolności radzenia sobie z rzeczywistym szumem danych. Wdrożone powinno być podejście hybrydowe z automatycznym pre-anotowaniem:

### Etap I: Przygotowanie szablonów (przy użyciu LLM)
Należy wykorzystać zewnętrzne modele (np. ChatGPT, Claude) do przygotowania kilkudziesięciu mocno zróżnicowanych wariantów tekstowych dla każdej z kategorii. Wszelkie konkretne dane osobowe muszą być w nich zastąpione markerami:
> *"Zgodnie z umową nr <MISC_FIN>, wypłacono wynagrodzenie na rachunek <ACCT> dla pracownika <PER> (adres: <LOC>)."*

### Etap II: Podstawianie wartości i wstrzykiwanie szumu (Python + Faker)
Następnie skrypt (korzystający z modułu `faker.providers.pl_PL`) dla każdego generowanego dokumentu (1-300):
1.  Losuje odpowiedni szablon dla danej kategorii.
2.  Tworzy autentycznie wyglądające polskie dane generowane matematycznie (np. polski numer konta o prawidłowej strukturze IBAN, poprawny PESEL, realnie brzmiący adres).
3.  **Wstrzykuje szum (Noise Injection) – to najważniejszy element testujący model NER!** 
    *   Wstawianie NIP-ów na różne sposoby: `123-456-78-90`, `123 456 78 90`, `1234567890`.
    *   Zaburzenie wielkości liter w nazwach firm i imionach.
    *   Symulacja "zepsutego OCR" (brak polskich znaków, literówki w słowach blisko NIP).

### Etap III: Auto-Anotacja (Golden Standard Generation)
Ogromna redukcja czasu pracy dla adnotatorów:
Ponieważ w kroku 2. to skrypt podmienia marker `<PER>` na wygenerowane nazwisko (np. `Jan Kowalski`), dokładnie zna on miejsce w łańcuchu znaków (*character offset*: *start*, *end*), w którym ten ciąg występuje po przetworzeniu szablonu. 
Podczas generowania skrypt nie tylko zapisuje tekst dokumentu, ale od razu wypluwa odpowiedni plik (np. JSONL z offsetami), gotowy do wczytania w programie anotacyjnym (np. Doccano/Label Studio). Rola adnotatorów ograniczy się w ten sposób wyłącznie do przeglądu i autoryzacji (zatwierdzenia) wyników, zamiast ręcznego zaznaczania każdej encji po kolei.

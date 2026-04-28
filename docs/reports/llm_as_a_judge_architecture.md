# Architektura Hybrydowej Detekcji PII: LLM-as-a-Judge

W architekturze hybrydowej detekcji PII, model LLM-as-a-judge nie powinien działać jako samodzielny skaner, lecz jako warstwa adjudykacji semantycznej, wywoływana selektywnie w sytuacjach niepewności lub konfliktu między szybszymi modelami (spaCy, Transformers) a regułami logicznymi.

Oto szczegółowy opis funkcjonowania tej warstwy w wersji hybrydowej:

## 1. Mechanizm selektywnego wyzwalania (UDRIL)
Zamiast analizować każdy fragment tekstu, system stosuje podejście **Uncertainty-DRIven LLM triggering (UDRIL)**. LLM jest aktywowany tylko wtedy, gdy:
- **Niska ufność:** Silnik NLP (HerBERT/RoBERTa) zwraca wynik z prawdopodobieństwem w „szarej strefie” (np. $0.3 < score < 0.7$).
- **Konflikt modeli:** Reguły logiczne (Regex + Checksum) wykryły wzorzec (np. NIP), ale model ML nie oznaczył go jako PII, lub odwrotnie.
- **Niejasność semantyczna:** Wykryto słowo słownikowo będące imieniem, ale o rzadkiej odmianie lub występujące w kontekście sugerującym nazwę pospolitą (np. „janusz biznesu”).

## 2. Kontekstowa weryfikacja (Semantic Adjudication)
Dla każdego podejrzanego fragmentu (tzw. span), system wycina okno kontekstowe (zazwyczaj jedno zdanie przed i po encji) i przesyła je do modelu LLM wraz ze specjalistycznym promptem. Zadaniem sędziego jest:
- **Analiza plauzibilności:** Sprawdzenie, czy np. 11-cyfrowy numer w danym otoczeniu lingwistycznym faktycznie pełni funkcję identyfikatora PESEL, czy jest technicznym numerem seryjnym urządzenia.
- **Ustalenie granic encji:** Skorygowanie błędów modeli transformatorowych, które często pomijają człony nazw firm (np. wyłapanie pełnej nazwy „Biuro Rachunkowe Cyfra Sp. z o.o.” zamiast samej „Cyfry”).

## 3. Metodologia oceniania (Rubric-based Grading)
W badaniach naukowych zaleca się, aby LLM-sędzia korzystał z predefiniowanej rubryki ocen (scoring rubric), która standaryzuje jego werdykty. Model nie zwraca tylko "tak/nie", ale ocenia encję według kryteriów:
- **Zgodność z typem:** Czy fragment pasuje do definicji PERSON/ORG/LOC?
- **Unikalność:** Czy fragment pozwala na faktyczną identyfikację osoby w tym kontekście?
- **Logika CoT:** Model musi najpierw przeprowadzić Chain-of-Thought (rozumowanie krok po kroku), co drastycznie redukuje halucynacje i zwiększa stabilność ocen.

## 4. Wyjście strukturalne i rozstrzyganie sporów
Wynik adjudykacji musi być zwracany w formacie JSON, co umożliwia automatyczną integrację z resztą potoku. W przypadku rozbieżności, system hybrydowy stosuje politykę:
- **Tryb rygorystyczny (Recall-oriented):** Jeśli LLM potwierdzi PII, encja jest anonimizowana, nawet jeśli bazowy model jej nie ujął.
- **Tryb precyzyjny (Precision-oriented):** Jeśli LLM odrzuci encję (oznaczy jako False Positive), zostaje ona usunięta z listy do anonimizacji, co chroni kontekst merytoryczny tekstu.

## 5. Ewaluacja sędziego (Alignment)
W pracy badawczej kluczowe jest zmierzenie zgodności sędziego z człowiekiem (**Human-LLM Alignment**). Wykorzystuje się do tego metryki takie jak Scott’s Pi lub Cohen’s Kappa, które sprawdzają, czy sędzia podejmuje decyzje w sposób powtarzalny i zbliżony do eksperta dziedzinowego. Udowodnienie wysokiej korelacji (alignment > 0.8) pozwala na uznanie modelu LLM za wiarygodne narzędzie do skalowalnej weryfikacji dużych zbiorów danych PII.

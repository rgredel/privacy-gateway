# Streszczenie / Abstract

## Streszczenie (język polski)

**Temat:** Privacy Gateway: Wieloagentowy system ochrony prywatności danych w strumieniach przetwarzania LLM oparty na hybrydowej detekcji PII z mechanizmem UDRIL

Niniejsza praca dyplomowa prezentuje projekt, implementację oraz ewaluację eksperymentalną systemu **Privacy Gateway** – wieloagentowego rozwiązania opartego na frameworku **LangGraph**. System został zaprojektowany w celu bezpiecznego i zautomatyzowanego przetwarzania danych osobowych oraz wrażliwych (PII – *Personally Identifiable Information*) w polskich dokumentach finansowo-księgowych (np. fakturach, potwierdzeniach przelewów, transkrypcjach OCR, umowach cywilnoprawnych i korespondencji mailowej) przed ich przekazaniem do zewnętrznych chmurowych modeli językowych (LLM), takich jak Google Gemini.

Głównym wyzwaniem podjętym w pracy jest optymalizacja kompromisu między bezpieczeństwem danych a zachowaniem użyteczności (*privacy-utility trade-off*) przetwarzanego tekstu dla modelu docelowego, przy jednoczesnym zapewnieniu odporności na ataki typu *prompt injection* i *jailbreaking*. Zaproponowane rozwiązanie bazuje na zasadach czystej architektury (*Clean Architecture*) i wykorzystuje **hybrydowy silnik detekcji PII** o następującej strukturze:
1.  **Zintegrowany zespół modeli NER (Ensemble NER Engine):** Łączy polski model transformerowy HerBERT, potok lingwistyczny spaCy (`pl_core_news_lg`) oraz deterministyczne reguły walidacyjne (wyrażenia regularne połączone z weryfikacją cyfr kontrolnych systemów PESEL, NIP, REGON, IBAN przy użyciu biblioteki `stdnum`) w celu maksymalizacji czułości detekcji (*Recall*).
2.  **Semantyczny sędzia LLM (LLM-as-a-Judge):** Uruchamiany selektywnie na podstawie autorskiej reguły **UDRIL** (*Uncertainty-DRIven LLM triggering*). Sędzia LLM, wykorzystując technikę wnioskowania krok po kroku (*Chain-of-Thought*), rozstrzyga spory w tzw. „szarej strefie” ufności modeli NER (prawdopodobieństwo 0,3–0,7), przy konfliktach werdyktów poszczególnych modeli oraz niejednoznacznościach semantycznych. W celu ochrony prywatności i redukcji kosztów finansowych, do sędziego przesyłane są jedynie zredukowane algorytmicznie fragmenty zdań zawierające potencjalne PII.
3.  **Wejściowy agent bezpieczeństwa (Guardrail Agent):** Działa równolegle do procesu detekcji PII, wykorzystując wyspecjalizowany klasyfikator `Meta-Llama-Prompt-Guard` do natychmiastowego blokowania złośliwych zapytań (*Prompt Injection*) przed wysłaniem ich do chmury.
4.  **Zintegrowany procesor dokumentów:** Wykorzystuje narzędzie `PyMuPDF4LLM` do konwersji plików PDF/obrazów na ustrukturyzowany format Markdown, zachowując czytelność tabel i układu dokumentu dla modeli językowych.

Wdrożony system poddano rygorystycznym badaniom eksperymentalnym na syntetycznym zbiorze 300 dokumentów finansowych (ok. 50 tys. tokenów), symulującym realną strukturę danych w biurze rachunkowym. Wyniki ewaluacji wykazały, że:
-   **Hybrydowy model z sędzią Gemini 2.5 Flash** osiąga **F1-score na poziomie 0,8886** (Precision: 0,9165, Recall: 0,8623) oraz **Utility Score na poziomie 0,8756**. Wykazuje on wyższą precyzję i lepsze zachowanie spójności informacyjnej w porównaniu do klasycznego zespołu NER (F1: 0,9069, Utility: 0,8434), skutecznie odrzucając fałszywe wykrycia (*False Positives*) i zapobiegając nadmiernemu maskowaniu.
-   **Odporność na ataki typu Prompt Injection** wyniosła **100% (ASR = 0,0%)** przy zerowym wskaźniku fałszywych alarmów dla zapytań bezpiecznych (**FPR = 0,0%**).
-   **Użycie lokalnego modelu Bielik 1.5B** w trybie sekwencyjnym skutkowało znaczącym spadkiem skuteczności (F1: 0,3151) oraz wysokim narzutem czasowym (średnia latencja: 16,23 s). Sformułowano w związku z tym plan optymalizacji w oparciu o architektoniczny wzorzec *Map-Reduce* (asynchroniczne zrównoleglenie).

Wnioski z pracy potwierdzają, że hybrydowa architektura orkiestrowana przez grafy stanów stanowi efektywne i skalowalne narzędzie do integracji systemów ERP z technologią LLM, gwarantując pełną zgodność z regulacjami RODO bez utraty analitycznych zdolności modeli generatywnych.

**Słowa kluczowe:** ochrona prywatności, PII, deidentyfikacja, deanonimizacja, systemy wieloagentowe, LangGraph, LLM-as-a-Judge, UDRIL, Prompt Injection, HerBERT, Bielik, Clean Architecture.

---

## Abstract (English)

**Title:** Privacy Gateway: A Multi-Agent System for Privacy-Preserving LLM Processing with Hybrid PII Detection and UDRIL Mechanism

This thesis presents the design, implementation, and experimental evaluation of **Privacy Gateway** – a multi-agent system built on the **LangGraph** framework. The system is designed to securely and automatically process Personally Identifiable Information (PII) in Polish financial and accounting documents (e.g., invoices, transaction confirmations, OCR transcripts, civil law contracts, and email correspondence) before transmitting them to external cloud-based Large Language Models (LLMs) such as Google Gemini.

The primary challenge addressed in this work is optimizing the *privacy-utility trade-off* of the processed text for the target model, while simultaneously ensuring robustness against *prompt injection* and *jailbreaking* attacks. The proposed solution is based on the principles of **Clean Architecture** and employs a **hybrid PII detection engine** with the following structure:
1.  **Ensemble NER Engine:** Combines the Polish HerBERT transformer model, the spaCy linguistic pipeline (`pl_core_news_lg`), and deterministic validation rules (regular expressions paired with check digit verification for PESEL, NIP, REGON, and IBAN numbers using the `stdnum` library) to maximize detection sensitivity (*Recall*).
2.  **Semantic LLM-as-a-Judge:** Triggered selectively based on a custom **UDRIL** (*Uncertainty-DRIven LLM triggering*) rule. Utilizing a *Chain-of-Thought* reasoning technique, the LLM Judge resolves disputes in the NER models' confidence "grey zone" (probability 0.3–0.7), model verdict conflicts, and semantic ambiguities. To preserve privacy and minimize financial costs, only algorithmically reduced sentence fragments containing candidate PII are sent to the LLM.
3.  **Input Security Guardrail (Guardrail Agent):** Operates in parallel with the PII detection process, utilizing a specialized `Meta-Llama-Prompt-Guard` classifier to immediately block malicious requests (*Prompt Injection*) before any data reaches the cloud.
4.  **Integrated Document Processor:** Employs the `PyMuPDF4LLM` tool to convert PDFs and images into structured Markdown, preserving the readability of tables and layouts for language models.

The implemented system was subjected to rigorous experimental testing on a synthetic dataset of 300 financial documents (approx. 50,000 tokens), simulating the actual data structure in an accounting office. The evaluation results demonstrated that:
-   **The hybrid model with a Gemini 2.5 Flash Judge** achieves an **F1-score of 0.8886** (Precision: 0.9165, Recall: 0.8623) and a **Utility Score of 0.8756**. It demonstrates higher precision and better preservation of informational coherence compared to the classic Ensemble NER (F1: 0.9069, Utility: 0.8434), effectively filtering out false detections (*False Positives*) and preventing over-masking.
-   **Robustness against Prompt Injection attacks** reached **100% (ASR = 0.0%)** with a zero false positive rate for benign queries (**FPR = 0.0%**).
-   **The use of a local Bielik 1.5B model** in sequential mode resulted in a significant drop in effectiveness (F1: 0.3151) and high computational overhead (mean latency: 16.23 s), leading to a proposed optimization plan based on a *Map-Reduce* architectural pattern (asynchronous parallelization).

The conclusions of this study confirm that a hybrid architecture orchestrated by state graphs is an effective and scalable tool for integrating ERP systems with LLM technology, ensuring full compliance with GDPR regulations without compromising the analytical capabilities of generative models.

**Keywords:** privacy protection, PII, de-identification, de-anonymization, multi-agent systems, LangGraph, LLM-as-a-Judge, UDRIL, Prompt Injection, HerBERT, Bielik, Clean Architecture.

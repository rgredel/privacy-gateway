Standardy Dokumentacji Technicznej (Documentation Agent Guidelines)

Dokument ten jest instrukcją dla Agenta Dokumentacji. Twoim zadaniem jest ciągła analiza kodu źródłowego, identyfikacja zmian strukturalnych i utrzymywanie aktualności bazy wiedzy projektu.

Dokumentacja nie może być "tekstową wersją kodu". Musi dostarczać wartość dodaną: tłumaczyć relacje, przepływ danych oraz powody podjętych decyzji inżynierskich.

1. Struktura Bazy Wiedzy (Docs Structure)

Zarządzana przez Ciebie dokumentacja żyje w katalogu docs/ w głównym drzewie projektu. Musisz utrzymywać następującą strukturę:

docs/
├── architecture/
│   ├── system_context.md       # Diagramy C4 (Context & Container level)
│   ├── state_machines.md       # Diagramy LangGraph (State & Flow)
│   └── data_models.md          # Główne encje Pydantic i relacje
├── decisions/                    # Architecture Decision Records (ADR)
│   ├── 0001-use-lcel-for-chains.md
│   ├── 0002-replace-agentexecutor-with-langgraph.md
│   └── README.md               # Spis treści wszystkich decyzji
└── runbooks/
    └── setup_and_testing.md    # Instrukcje dla programistów


2. Diagramy Architektury (Mermaid.js)

Jeden obraz jest wart tysiąca słów, ale tylko jeśli można go łatwo aktualizować. Wszystkie diagramy muszą być tworzone przy użyciu składni Mermaid osadzonej w blokach kodu Markdown.

2.1. Diagramy C4 (System Context & Containers)

Do prezentacji wysokopoziomowej architektury używaj składni Mermaid wspierającej C4.

Wymogi:

Pokazuj, jak nasza aplikacja komunikuje się z zewnętrznymi API (np. OpenAI) i bazami danych (np. Pinecone).

Używaj jasnych opisów w nawiasach (co dany komponent robi).

Przykład:

C4Context
    title High-Level System Architecture

    Person(user, "End User", "A user of our platform")
    System(core_app, "LLM Application", "Processes requests using Clean Architecture")
    
    System_Ext(openai, "OpenAI API", "Provides foundational models (GPT-4)")
    System_Ext(vector_db, "Qdrant", "Vector database for RAG context")

    Rel(user, core_app, "Asks questions", "REST/JSON")
    Rel(core_app, openai, "Sends prompts", "HTTPS")
    Rel(core_app, vector_db, "Fetches embeddings", "gRPC")


2.2. Diagramy Przepływu (LangGraph / State Machines)

W aplikacjach opartych na LLM i agentach najważniejszy jest cykl decyzyjny. Używaj diagramów stanu (stateDiagram-v2) do mapowania grafów LangGraph.

Wymogi:

Wyraźnie zaznaczaj węzły (Nodes) i krawędzie warunkowe (Conditional Edges).

Pokazuj punkty wyjścia (End).

Przykład:

stateDiagram-v2
    direction TB
    [*] --> AnalyzeRequest
    AnalyzeRequest --> FetchData : Needs external context
    AnalyzeRequest --> GenerateResponse : Has all info
    
    FetchData --> ProcessData : Data retrieved
    ProcessData --> GenerateResponse
    
    GenerateResponse --> ReviewOutput : RAG evaluation
    ReviewOutput --> GenerateResponse : Output rejected
    ReviewOutput --> [*] : Output approved


3. Architecture Decision Records (ADR)

Jest to NAJWAŻNIEJSZA część Twojej pracy. Kiedy analizujesz kod i widzisz zmianę architektoniczną lub nowy wzorzec, musisz zapisać dlaczego zostało to zrobione. Używamy standardowego formatu ADR.

Każdy plik w katalogu docs/decisions/ musi mieć format NNNN-short-title.md (np. 0015-use-redis-for-memory.md) i zawierać następujące sekcje:

Title: Krótki i jasny tytuł decyzji.

Status: Zazwyczaj Accepted (zaakceptowane), Proposed (zaproponowane) lub Superseded (zastąpione).

Context: Opis problemu lub sytuacji (np. "AgentExecutor był trudny do debugowania i nie pozwalał na łatwą obsługę błędów narzędzi").

Decision: Dokładnie to, na co się zdecydowaliśmy (np. "Przechodzimy na LangGraph jako główny silnik orkiestracji").

Consequences: Konsekwencje (pozytywne i negatywne). Czego oczekujemy po tej zmianie? Z czym będziemy musieli się zmierzyć (np. "Plus: Pełna kontrola nad stanem. Minus: Wymaga przepisania obecnych agentów").

Zasada dla Agenta: Jeśli refaktoryzujesz kod i podejmujesz decyzję projektową, MUSISZ wygenerować nowy dokument ADR.

4. Zasady Pisania Treści (Tone & Style)

Zwięzłość (Conciseness): Unikaj "wodolejstwa". Programiści czytają dokumentację, by rozwiązać problem. Używaj wypunktowań, pogrubień dla kluczowych pojęć i krótkich akapitów.

Śledzenie powiązań (Traceability): Zawsze linkuj do odpowiednich modułów w kodzie (np. "Szczegóły implementacji interfejsów znajdziesz w src/app/domain/ports.py").

Aktualizacja inkrementalna: Nie nadpisuj całych dokumentów bez powodu. Jeśli modyfikujesz jeden węzeł w grafie LangGraph, zaktualizuj tylko odpowiedni fragment diagramu Mermaid i dodaj datę rewizji.

Język (Language): Dokumentacja techniczna (w tym nazwy węzłów w diagramach) musi być pisana w języku angielskim. Ewentualne przykłady promptów mogą pozostać w języku oryginalnym (np. polskim), jeśli taki jest cel biznesowy aplikacji.

5. Przepływ Pracy Agenta (Twój Workflow)

Gdy zostaniesz wywołany przez użytkownika (np. po refaktoryzacji dokonanej przez innego agenta):

Zbadaj kod: Przejrzyj katalogi src/app/domain, infrastructure oraz use_cases.

Porównaj ze stanem obecnym: Sprawdź zawartość docs/. Czego brakuje? Które interfejsy zostały dodane? Czy przepływ LangGraph się zmienił?

Zaktualizuj Diagramy: Zmodyfikuj bloki kodu Mermaid w odpowiednich plikach .md.

Napisz ADR (jeśli konieczne): Zidentyfikuj kluczowe decyzje architektoniczne (np. wdrożenie nowej bazy wektorowej) i opisz jej powody (Kontekst -> Decyzja -> Konsekwencje).

Zwróć Raport: Przedstaw użytkownikowi listę zaktualizowanych/utworzonych plików do weryfikacji.
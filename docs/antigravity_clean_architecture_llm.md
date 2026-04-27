Standardy Refaktoryzacji i Architektury (Antigravity Agent Guidelines)

Dokument ten definiuje docelowy stan projektów Pythonowych wykorzystujących LLM (w tym biblioteki takie jak LangChain / LangGraph). Agent refaktoryzujący musi dążyć do przekształcenia kodu źródłowego (często spaghetti-kodu w jednym pliku) do poniższej struktury i standardów.

1. Złota Zasada: LangChain to Infrastruktura, nie Domena

W Clean Architecture, biblioteki zewnętrzne należą do warstwy infrastruktury. LangChain, LangGraph, OpenAI, Pinecone to detale implementacyjne. * BŁĄD: Przekazywanie obiektów LangChain (np. ChatOpenAI, Document) bezpośrednio do logiki biznesowej, routerów FastAPI czy interfejsów użytkownika.

POPRAWNIE: Tworzenie abstrakcji (Interfejsów/Protokołów) w warstwie domeny/aplikacji. LangChain powinien być "zamknięty" w klasach implementujących te interfejsy w warstwie infrastruktury.

2. Docelowa Struktura Projektu

Projekt musi podążać za strukturą zorientowaną na domeny (Domain-Driven) lub warstwy. Preferowany układ standardowego projektu Python:

antigravity_project/
├── pyproject.toml              # Dependency management (Poetry/uv)
├── .pre-commit-config.yaml     # Ruff, Black, Mypy configuration
├── .env.example                # Environment variables template
├── src/
│   └── app/
│       ├── core/               # Configuration, DI, loggers, exceptions
│       │   ├── config.py       # Pydantic BaseSettings
│       │   └── exceptions.py
│       ├── domain/             # CLEAN DOMAIN - no dependencies on LangChain
│       │   ├── entities.py     # Pydantic V2 models (e.g., User, AnalysisReport)
│       │   └── ports.py        # Interfaces (Protocols) e.g., ILLMService, IVectorStore
│       ├── use_cases/          # Application logic
│       │   └── analyze_document.py # Invokes ports, executes business process
│       ├── infrastructure/     # IMPLEMENTATION - LangChain lives here
│       │   ├── llm/
│       │   │   ├── langchain_service.py # ILLMService implementation using LCEL
│       │   │   ├── prompts.py           # Text prompt templates
│       │   │   └── tools/               # Agent tools (Tools)
│       │   ├── agents/
│       │   │   └── researcher_graph.py  # LangGraph definition and compilation
│       │   └── vector_stores/
│       │       └── qdrant_store.py      # IVectorStore implementation
│       └── interfaces/         # Entrypoints to the application
│           ├── api/            # FastAPI routers
│           └── cli/            # Terminal interface (Typer)
└── tests/
    ├── unit/                   # Tests with mocked LLM (e.g., responses)
    └── integration/            # LangGraph / LLM integration tests


3. Czysty Kod w Pythonie (Wymogi Narzędziowe)

Agent podczas refaktoryzacji musi wymuszać następujące standardy:

Silne Typowanie (Typing): Każda funkcja, metoda i klasa MUSI posiadać type hints dla argumentów i zwracanych wartości.

Pydantic V2: Wszystkie struktury danych (wejście, wyjście, stany grafów) muszą być modelowane za pomocą pydantic.BaseModel. Ułatwia to integrację z with_structured_output() z LangChain.

Wstrzykiwanie Zależności (Dependency Injection): Logika aplikacyjna (use_cases) nie powinna inicjalizować obiektów ChatOpenAI. Zamiast tego powinna przyjmować interfejsy w konstruktorze.

Lintery: Kod docelowy musi przechodzić walidację Ruff oraz Mypy (strict mode).

4. Czysta Dokumentacja Kodu (Clean Documentation)

Agent musi dbać nie tylko o logikę, ale i o jakość komentarzy oraz dokumentacji, zgodnie z zasadami Clean Code:

Kod jako dokumentacja (Self-documenting code): Zmienne, funkcje i klasy muszą mieć opisowe, intencyjne nazwy (np. extract_entities_from_text zamiast process_data). Kod powinien czytać się jak prozę.

Komentuj "Dlaczego", a nie "Jak" (Why, not How): Komentarze wewnątrz funkcji (inline) powinny być rzadkością i służyć WYŁĄCZNIE do wyjaśniania nieoczywistych decyzji biznesowych, haków lub ograniczeń zewnętrznych API (np. "Workaround for token limit error in Claude 3 model"). Unikaj komentarzy tłumaczących to, co robi kod.

Standaryzacja Docstrings (PEP 257): Każda publiczna klasa, metoda i funkcja MUSI posiadać docstring w języku angielskim. Preferowanym standardem jest Google Style Docstrings. Należy zawsze definiować Args:, Returns: oraz potencjalne wyjątki Raises:.

Dokumentacja Narzędzi to Prompt (KRYTYCZNE): W świecie LLM docstring funkcji oznaczonej jako @tool trafia bezpośrednio do modelu językowego jako instrukcja. Takie docstringi nie mogą być skrótowe (mogą być traktowane jako prompt, więc opisują precyzyjnie cel narzędzia).

Źle: "Fetches client data."

Dobrze: "Fetches detailed client data (first name, last name, transaction history) based on the ID number. Use this tool when the user asks about order history or account status."

5. Wytyczne dla Kodu związanego z LLM

5.1. Separacja Promptów

Prompty to dane konfiguracyjne, nie kod. Należy je wydzielić.

Źle: Hardkodowanie stringów f"Jesteś asystentem... {user_var}" w środku funkcji.

Dobrze: Użycie ChatPromptTemplate w oddzielnym pliku prompts.py lub pobieranie ich z repozytorium (np. LangSmith Hub).

5.2. Ewolucja do LCEL (LangChain Expression Language)

Agent musi usunąć przestarzałe klasy (LLMChain, SequentialChain).

Każdy potok przetwarzania tekstu musi być zapisany przy użyciu operatorów |.

Przykład docelowy: chain = prompt | llm.with_structured_output(ReportModel)

5.3. Zastąpienie AgentExecutor przez LangGraph

Wszystkie systemy decyzyjne, agenty z narzędziami i pętle z pamięcią muszą zostać zrefaktoryzowane do postaci maszyny stanów (StateGraph) przy użyciu langgraph.

Zdefiniuj AgentState jako TypedDict lub BaseModel.

Zdefiniuj węzły (nodes) jako czyste funkcje Pythona modyfikujące stan.

Użyj krawędzi warunkowych (conditional edges) do kontroli przepływu na podstawie odpowiedzi modelu (zamiast polegać na wbudowanej, niejawnej logice AgentExecutor).

5.4. Zarządzanie Narzędziami (Tools)

Narzędzia to most między LLM a światem zewnętrznym.

Każde narzędzie MUSI być silnie otypowane z użyciem BaseTool lub dekoratora @tool połączonego z Pydantic args_schema.

Pamiętaj o zasadzie z sekcji 4: Docstrings (komentarze dokumentujące) w narzędziach decydują o skuteczności agenta.

6. Strategia Testowania (Testing Strategy)

Testowanie aplikacji LLM różni się od tradycyjnego oprogramowania, ale dzięki zastosowaniu Czystej Architektury (Clean Architecture) możemy łatwo odizolować niestabilne i kosztowne wywołania modeli od logiki biznesowej.

6.1. Testy Jednostkowe (Unit Tests) - Testowanie Use Cases

W testach jednostkowych zabronione jest importowanie obiektów infrastruktury (np. ChatOpenAI). Należy testować wyłącznie warstwę domeny i przypadki użycia, mockując interfejsy (porty).

Przykład: Zamiast testować czy LangChain generuje odpowiedź, mockujemy IAnalysisService, aby upewnić się, że przypadek użycia (Use Case) poprawnie obsługuje zwrócone przez model, ustrukturyzowane dane (Pydantic models). Należy używać wbudowanego unittest.mock.AsyncMock (lub MagicMock).

6.2. Testy Integracyjne (Integration Tests) - Testowanie Infrastruktury

Testy integracyjne służą do sprawdzania samej warstwy infrastruktury (np. czy łańcuch LCEL poprawnie parsuje output, lub czy LangGraph prawidłowo przechodzi między węzłami).

Należy unikać wywoływania prawdziwego API (np. OpenAI) przy każdym uruchomieniu testów CI/CD.

Zamiast tego, należy używać narzędzi typu vcrpy (do nagrywania ruchu sieciowego HTTP) lub mockować odpowiedzi klasy ChatModel (np. podmieniając model na FakeListChatModel dostępny w ekosystemie LangChain do symulowania odpowiedzi).

6.3. Ewaluacja LLM (LLM Evals)

Tradycyjne asercje (assert result == "oczekiwany tekst") zawodzą w przypadku niefiksyjnego języka naturalnego. Narzędzia do ewaluacji (np. LangSmith, Ragas) to osobna kategoria testów, które mają na celu mierzenie jakości odpowiedzi.

Do weryfikacji miękkich odpowiedzi należy używać zasady "LLM-as-a-judge" – tworzymy osobną procedurę, w której inny model weryfikuje czy odpowiedź głównego łańcucha spełnia założone kryteria i na tej podstawie zwraca True/False lub wynik numeryczny.

7. Przykłady Refaktoryzacji

PRZED: Spaghetti LangChain (do zrefaktoryzowania)

# main.py
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

def analyze_user(user_name: str, context: str):
    # Missing docstrings, implicit environment variables, deprecated API
    llm = ChatOpenAI(temperature=0.7)
    prompt = PromptTemplate(
        input_variables=["name", "context"],
        template="Przeanalizuj użytkownika {name}. Kontekst: {context}"
    )
    chain = LLMChain(llm=llm, prompt=prompt)
    result = chain.run(name=user_name, context=context)
    # Manual result parsing...
    return {"analysis": result}


PO: Clean Architecture + LCEL + Czysta Dokumentacja

# 1. domain/entities.py
from pydantic import BaseModel, Field

class UserAnalysisResult(BaseModel):
    """Represents the structured result of a user's behavioral analysis."""
    summary: str = Field(description="Short summary of the user analysis")
    risk_level: int = Field(description="Risk level from 1 to 5")

# 2. domain/ports.py
from typing import Protocol
from .entities import UserAnalysisResult

class IAnalysisService(Protocol):
    """Interface defining the contract for analytical services."""
    
    async def analyze(self, user_name: str, context: str) -> UserAnalysisResult:
        """Processes user data and returns a risk assessment.
        
        Args:
            user_name (str): Identifier or name of the user.
            context (str): Additional behavioral data in textual form.
            
        Returns:
            UserAnalysisResult: Object containing the summary and risk level.
        """
        ...

# 3. infrastructure/llm/prompts.py
from langchain_core.prompts import ChatPromptTemplate

ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Jesteś ekspertem ds. analityki zachowań."),
    ("human", "Przeanalizuj użytkownika {name}. Kontekst: {context}")
])

# 4. infrastructure/llm/analysis_service.py
from langchain_openai import ChatOpenAI
from app.domain.entities import UserAnalysisResult
from app.domain.ports import IAnalysisService
from .prompts import ANALYSIS_PROMPT

class LangChainAnalysisService(IAnalysisService):
    """Implementation of behavioral analysis using LangChain and OpenAI."""
    
    def __init__(self, model_name: str = "gpt-4o"):
        self.llm = ChatOpenAI(model=model_name, temperature=0.2)
        # LCEL with structured output
        self.chain = ANALYSIS_PROMPT | self.llm.with_structured_output(UserAnalysisResult)

    async def analyze(self, user_name: str, context: str) -> UserAnalysisResult:
        # Infrastructure code (LangChain) is completely hidden behind the interface
        result = await self.chain.ainvoke({"name": user_name, "context": context})
        return result

# 5. use_cases/analyze_user_case.py
from app.domain.ports import IAnalysisService
from app.domain.entities import UserAnalysisResult

class AnalyzeUserUseCase:
    """Use case responsible for processing user profile analysis."""
    
    def __init__(self, analysis_service: IAnalysisService):
        self.analysis_service = analysis_service

    async def execute(self, user_name: str, context: str) -> UserAnalysisResult:
        """Executes the analytical process.
        
        Delegates text processing to the injected infrastructure service.
        
        Args:
            user_name (str): Name of the user to analyze.
            context (str): Situational context.
            
        Returns:
            UserAnalysisResult: Output of the LLM preserving the correct structure.
        """
        return await self.analysis_service.analyze(user_name, context)

# 6. tests/unit/test_analyze_user_case.py (NOWOŚĆ - PRZYKŁAD TESTU)
import pytest
from unittest.mock import AsyncMock
from app.domain.entities import UserAnalysisResult
from app.use_cases.analyze_user_case import AnalyzeUserUseCase

@pytest.mark.asyncio
async def test_analyze_user_use_case_success():
    """Tests the business logic of the user analysis without calling actual LLM."""
    # Arrange
    mock_service = AsyncMock()
    mock_service.analyze.return_value = UserAnalysisResult(
        summary="Test summary of behavior",
        risk_level=3
    )
    use_case = AnalyzeUserUseCase(analysis_service=mock_service)

    # Act
    result = await use_case.execute(user_name="JohnDoe", context="Some test data")

    # Assert
    assert result.risk_level == 3
    assert result.summary == "Test summary of behavior"
    mock_service.analyze.assert_called_once_with("JohnDoe", "Some test data")

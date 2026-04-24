from typing import TypedDict, Dict, Annotated
from langgraph.graph.message import add_messages

class GraphState(TypedDict):
    messages: Annotated[list, add_messages]  # Historia konwersacji (nowe!)
    raw_xml: str                         # Wejściowy plik XML jako czysty tekst (dla kontektu RAG)
    user_query: str                      # Pytanie zadane przez użytkownika
    raw_pii_strings: list[str]           # Zidentyfikowane informacje PII (surowe napisy z detekcji)
    labeled_pii_entities: list[dict]     # Ustrukturyzowane PII (z etykietami: value, label)
    masked_context: str                  # Tekst kontekstu po pseudonimizacji
    masked_query: str                    # Pytanie użytkownika po pseudonimizacji
    vault: Dict[str, str]                # Skarbiec kluczy: Token -> Oryginał
    is_safe: bool                        # Status weryfikacji Guardrail
    cloud_response: str                  # Wynik z zewnętrznego LLM (Gemini)
    final_output: str                    # Wynik u końcowego użytkownika (zdekodowany)
    error_status: str                    # Status błędu (np. błąd detekcji PII)
    # Konfiguracja agentów (z UI)
    enable_guardrail: bool               # Czy Guardrail Agent jest aktywny
    detection_mode: str                  # Tryb detekcji: 'hybrid' lub 'llm-only'
    show_debug: bool                     # Czy pokazywać logi debugowania
    cloud_query_debug: str               # Pełne zapytanie wysłane do chmury (do celów debugowania)

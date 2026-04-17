import os
from langgraph.graph import StateGraph, END
from state import GraphState
from agents import (
    retrieval_agent,
    detection_agent,
    masking_agent,
    guardrail_agent,
    check_guardrail,
    cloud_llm,
    block_request,
    re_identification_agent
)

# ==========================================
# 1. WARUNKI I GRAF
# ==========================================

def privacy_wrapper_agent(state: GraphState) -> GraphState:
    """Wraper łączący wczesniejszy proces logiki prywatności w jeden wątek operacyjny dla LangGraph"""
    detect_res = detection_agent(state)
    
    # Przekazujemy stan detekcji do wewnętrznego modelu
    internal_state = {**state, **detect_res}

    # FAIL-SAFE: Jeśli detekcja rzuciła błąd (error_status), nie wykonujemy maskowania
    if detect_res.get("error_status"):
        return detect_res

    mask_res = masking_agent(internal_state)
    
    # LangGraph Reducer na głównej ścieżce otrzyma scalone, wyselekcjonowane aktualizacje PII oraz masek
    return {**detect_res, **mask_res}


def sync_node(state: GraphState) -> GraphState:
    """Węzeł synchronizujący, zbiegają się tu równoległe wątki zabezpieczeń przed wejściem wyżej"""
    return state

def build_graph():
    workflow = StateGraph(GraphState)

    workflow.add_node("retrieval_agent", retrieval_agent)
    workflow.add_node("privacy_wrapper", privacy_wrapper_agent)
    workflow.add_node("guardrail_agent", guardrail_agent)
    workflow.add_node("sync_node", sync_node)
    
    workflow.add_node("cloud_llm", cloud_llm)
    workflow.add_node("block_request", block_request)
    workflow.add_node("re_identification_agent", re_identification_agent)

    workflow.set_entry_point("retrieval_agent")
    
    # 1. FAN-OUT (Współbieżność):
    # Guardrail oraz Privacy Wrapper (detekcja+maskowanie) działają w tle jednocześnie.
    workflow.add_edge("retrieval_agent", "privacy_wrapper")
    workflow.add_edge("retrieval_agent", "guardrail_agent")
    
    # 2. FAN-IN (Złączenie i Synchronizacja):
    workflow.add_edge("privacy_wrapper", "sync_node")
    workflow.add_edge("guardrail_agent", "sync_node")
    
    # 3. KONTROLA BEZPIECZEŃSTWA:
    workflow.add_conditional_edges(
        "sync_node", 
        check_guardrail, 
        {"cloud_llm": "cloud_llm", "blocked": "block_request"}
    )
    
    # 4. CHMURA I ROZKODOWANIE:
    workflow.add_edge("cloud_llm", "re_identification_agent")
    
    workflow.add_edge("re_identification_agent", END)
    workflow.add_edge("block_request", END)

    return workflow.compile()

# ==========================================
# 2. GŁÓWNA APLIKACJA / INTERFEJS
# ==========================================

# Wyeksportowana instancja dla LangGraph Studio (langgraph.json)
graph = build_graph()

if __name__ == "__main__":
    app = build_graph()
    print("\n[Start Systemu 'Privacy Gateway' z interaktywnym pytaniem do RAG]")
    print("------------------------------------------------------------------")
    
    try:
        with open("fake_data.xml", "r", encoding="utf-8") as f:
            xml_input = f.read()
            print("Pomyślnie załadowano 'fake_data.xml' jako bazę kontekstową.")
    except FileNotFoundError:
        xml_input = "<root><info>Brak danych</info></root>"
        print("Nie odnaleziono pliku 'fake_data.xml'.")

    while True:
        try:
            print("\n" + "="*50)
            user_query = input("Zadaj pytanie (np. 'Z kim powinienem się kontaktować?') lub wpisz 'exit': ")
        except EOFError:
            break
            
        if user_query.strip().lower() in ["exit", "quit", "wyjście", "wyjscie"]:
            print("Kończenie pracy.")
            break
            
        if not user_query.strip():
            continue
            
        initial_state = GraphState(
            raw_xml=xml_input,
            user_query=user_query,
            detected_pii=[],
            masked_context="",
            masked_query="",
            vault={},
            is_safe=False,
            cloud_response="",
            final_output=""
        )
        
        # Uruchomienie przepływu LangGraph
        print("\n[AI] Przetwarzanie zapytania przez agenty LangGraph...")
        final_state = app.invoke(initial_state)
        
        print("\n--- ODPOWIEDŹ Z GEN-AI ---")
        print(final_state.get("final_output"))
        
        print("\n--- ZA KULISAMI (Debug Systemu Ochrony Prywatności) ---")
        print("Skarbiec PII (Vault):", final_state.get("vault"))
        print("\nJakie pytanie uchronione od PII zobaczył dokładnie Gemini?")
        print("->", final_state.get("masked_query"))

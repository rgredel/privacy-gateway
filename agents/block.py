from state import GraphState

def block_request(state: GraphState) -> GraphState:
    """
    Przekierowanie jeśli Guardrail lub Fail-Safe zablokuje żądanie.
    """
    error = state.get("error_status")
    if error:
        return {"final_output": f"WYJĄTEK BEZPIECZEŃSTWA: System detekcji danych wrażliwych jest niedostępny. ({error})"}
        
    return {"final_output": "ZABLOKOWANO: Wykryto próbę Prompt Injection lub niebezpieczne żądanie."}


from state import GraphState

def masking_agent(state: GraphState) -> GraphState:
    """
    Pseudonimizacja. Zastępuje znalezione PII tokenami w zapytaniu i kontekście.
    """
    vault = state.get("vault", {})
    masked_context = state["raw_xml"]
    masked_query = state["user_query"]
    
    print("\n" + "-"*30)
    print("[DEBUG: MASKING] Rozpoczęto maskowanie danych...")
    
    for idx, pii in enumerate(state.get("detected_pii", [])):
        token = f"[PII_{idx}]"
        vault[token] = pii
        
        # Ochrona kontekstu
        masked_context = masked_context.replace(pii, token)
        # Ochrona pytania zadanego przez użytkownika
        masked_query = masked_query.replace(pii, token)

    print(f"[DEBUG: MASKING] Skarbiec (Vault): {vault}")
    print(f"[DEBUG: MASKING] Zanonimizowane zapytanie: {masked_query}")
    print("-"*30)

    return {"masked_context": masked_context, "masked_query": masked_query, "vault": vault}

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
    
    # Używamy ustrukturyzowanych encji z etykietami (z labeling_agent), jeśli są dostępne
    entities = state.get("labeled_pii_entities", [])
    
    if entities:
        for idx, entity in enumerate(entities):
            val = entity["value"]
            lbl = entity["label"]
            token = f"[{lbl.upper()}_{idx}]"
            vault[token] = val
            masked_context = masked_context.replace(val, token)
            masked_query = masked_query.replace(val, token)
    else:
        # Fallback do prostego maskowania, jeśli brak ustrukturyzowanych danych
        for idx, pii in enumerate(state.get("raw_pii_strings", [])):
            token = f"[PII_{idx}]"
            vault[token] = pii
            masked_context = masked_context.replace(pii, token)
            masked_query = masked_query.replace(pii, token)

    print(f"[DEBUG: MASKING] Skarbiec (Vault): {vault}")
    print(f"[DEBUG: MASKING] Zanonimizowane zapytanie: {masked_query}")
    print("-"*30)

    return {"masked_context": masked_context, "masked_query": masked_query, "vault": vault}

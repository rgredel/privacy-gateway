from state import GraphState

def re_identification_agent(state: GraphState) -> GraphState:
    """
    Przywraca oryginalne wartości z usuniętymi tokenizacjami, przed zwrotem do użytkownika.
    """
    cloud_resp = state.get("cloud_response", "")
    vault = state.get("vault", {})
    
    final_resp = cloud_resp
    print("\n" + "🔓"*20)
    print("[DEBUG: RE-ID] Przywracanie danych PII do odpowiedzi...")
    for token, original_value in vault.items():
        final_resp = final_resp.replace(token, original_value)
        
    print(f"[DEBUG: RE-ID] Końcowy wynik: {final_resp}")
    print("🔓"*20 + "\n")
    
    return {"final_output": final_resp}

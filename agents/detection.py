from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from state import GraphState
from llm_factory import get_local_llm
from agents.presidio_engine import get_pii_candidates

class PIIData(BaseModel):
    detected_strings: list[str] = Field(description="Lista fragmentów tekstu będących danymi PII.")

def detection_agent(state: GraphState) -> GraphState:
    """
    Wykorzystuje lokalny model Bielik poprzez Ollama do detekcji PII.
    """
    text_to_analyze = state["raw_xml"] + "\n\nPYTANIE UZYTKOWNIKA:\n" + state["user_query"]
    
    print("\n" + "="*50)
    print("[DEBUG: DETECTION] Rozpoczęto analizę PII przez model Bielik...")
    # print(f"[DEBUG: DETECTION] Tekst wejściowy:\n{text_to_analyze}") # Opcjonalnie wyłączone dla czytelności
        
    try:
        llm = get_local_llm()
        structured_llm = llm.with_structured_output(PIIData)
        
        prompt = PromptTemplate.from_template(
            "Jesteś ekspertem ds. ochrony danych osobowych (DPO). Twoim zadaniem jest precyzyjna identyfikacja danych PII.\n\n"
            "Zadanie: Wyodrębnij tylko INDYWIDUALNE dane osobowe (PII) z poniższego tekstu.\n\n"
            "Zasady:\n"
            "1. Zwracaj tylko konkretne wartości. Pomiń etykiety (np. 'PESEL:', 'Kontakt:').\n"
            "2. Odrzucaj dane instytucji publicznych i postaci historycznych.\n"
            "3. Podejście konserwatywne: Jeśli nie masz pewności, pomiń fragment.\n\n"
            "Format wyjściowy: Zwróć dane jako listę fragmentów tekstu, np. ['Wartość 1', 'Wartość 2'].\n\n"
            "TEKST DO ANALIZY:\n{text}"
        )
        
        chain = prompt | structured_llm
        result = chain.invoke({"text": text_to_analyze})
        detected = result.detected_strings if result else []
        error_msg = ""
    except Exception as e:
        error_msg = f"Detection failed: {e}"
        print(f"[Blad] Modul Detekcji zawiodl: {e}")
        detected = []
        
    unique_pii = list(set([p.strip() for p in detected if p.strip()]))
    
    print(f"[DEBUG: DETECTION] Wykryte PII: {unique_pii}")
    print("="*50)
    
    return {
        "detected_pii": unique_pii,
        "error_status": error_msg
    }

def hybrid_detection_agent(state: GraphState) -> GraphState:
    """
    Logika scalająca (Merging Strategy):
    1. Presidio znajduje wzorce (numery), którym ufamy.
    2. LLM szuka wyłącznie nazwisk i adresów osób prywatnych.
    3. Wyniki są łączone.
    """
    raw_text = state["raw_xml"] + "\n" + state["user_query"]
    
    print("\n" + "="*50)
    print("[DEBUG: HYBRID] Rozpoczęto analizę hybrydową (Strategia Merging)...")
    
    # 1. Kandydaci z Presidio (numeryczne)
    presidio_pii = get_pii_candidates(raw_text)
    print(f"[DEBUG: HYBRID] Presidio znalazło: {presidio_pii}")
    
    # 2. LLM szuka tylko nazwisk i adresów
    try:
        llm = get_local_llm()
        structured_llm = llm.with_structured_output(PIIData)
        
        prompt = PromptTemplate.from_template(
            "Jesteś ekspertem ds. cyberbezpieczeństwa i prywatności danych. Twoim celem jest uzupełnienie detekcji PII o brakujące nazwiska i adresy.\n\n"
            "Zadanie: W poniższym tekście znajdź tylko IMIONA, NAZWISKA i ADRESY osób prywatnych.\n\n"
            "ZASADY:\n"
            "1. Ignoruj numery (NIP, PESEL, IBAN) - są już przetworzone.\n"
            "2. Odrzucaj postacie historyczne i nazwy instytucji publicznych.\n"
            "3. Zwracaj tylko konkretne wartości bez etykiet.\n\n"
            "Format wyjściowy: Lista fragmentów tekstu, np. ['Wartość A', 'Wartość B'].\n\n"
            "TEKST DO ANALIZY:\n{text}"
        )
        
        chain = prompt | structured_llm
        result = chain.invoke({"text": raw_text})
        llm_detected = result.detected_strings if result else []
    except Exception as e:
        print(f"[Blad] LLM zawiódł w hybrydzie: {e}")
        llm_detected = []

    # 3. Łączenie wyników
    final_pii = list(set(presidio_pii + llm_detected))
    unique_pii = list(set([p.strip() for p in final_pii if p.strip()]))
    
    print(f"[DEBUG: HYBRID] Ostateczne PII (Merge): {unique_pii}")
    print("="*50)
    
    return {
        "detected_pii": unique_pii,
        "error_status": ""
    }

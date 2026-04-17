from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from state import GraphState
from llm_factory import get_local_llm
from agents.presidio_engine import get_pii_candidates

class PIIData(BaseModel):
    detected_strings: list[str] = Field(description="Lista fragmentów tekstu będących danymi PII.")

def detection_agent(state: GraphState) -> GraphState:
    """
    Agent detekcji PII oparty wyłącznie na LLM (Bielik).
    """
    text_to_analyze = state["raw_xml"] + "\n" + state["user_query"]
    
    print("\n" + "="*50)
    print("[DEBUG: DETECTION] Rozpoczęto analizę PII przez model Bielik...")
    
    try:
        llm = get_local_llm()
        structured_llm = llm.with_structured_output(PIIData)
        
        prompt = PromptTemplate.from_template(
            "Zadanie: Jesteś ekspertem RODO. Znajdź w tekście dane PII TYLKO prywatnych osób fizycznych.\n\n"
            "### ZASADY SELEKCJI:\n"
            "1. TYLKO WARTOŚCI: Wypisz sam numer lub nazwisko (np. '5210001234', a nie 'NIP: 5210001234').\n"
            "2. OSOBY PRYWATNE: Ignoruj postacie historyczne (np. Kopernik), firmy (np. Orlen) i urzędy.\n"
            "3. ADRESY: Ignoruj adresy publiczne (np. Wiejska 4, Wawel) i nazwy miast jako osobne encje.\n"
            "4. STOP META-DATA: Słowa takie jak 'PESEL', 'NIP', 'Email', 'Telefon' to ETYKIETY - NIGDY ich nie wypisuj.\n\n"
            "### PRZYKŁADY NEGATYWNE (Tego NIE wypisuj):\n"
            "- 'Mikołaj Kopernik' -> (ignoruj, postać historyczna)\n"
            "- 'Urząd Skarbowy' -> (ignoruj, instytucja)\n"
            "- 'NIP', 'PESEL' -> (ignoruj, to nazwa kategorii)\n"
            "- 'System RAG' -> (ignoruj, termin techniczny)\n\n"
            "### PRZYKŁADY POZYTYWNE (To wypisz):\n"
            "- 'Jan Nowak' -> Jan Nowak\n"
            "- 'ul. Kwiatowa 2/4, 00-123 Warszawa' -> ul. Kwiatowa 2/4, 00-123 Warszawa\n\n"
            "TEKST DO ANALIZY:\n{text}"
        )
        
        chain = prompt | structured_llm
        result = chain.invoke({"text": text_to_analyze})
        detected = result.detected_strings if result else []
        error_msg = ""
    except Exception as e:
        error_msg = f"Detection failed: {e}"
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
    Logika Sekwencyjna (Sequential Verification & Discovery):
    1. Presidio znajduje kandydatów (wzorce numeryczne, adresy e-mail).
    2. Kandydaci są przekazywani do Bielika jako kontekst.
    3. Bielik weryfikuje kandydatów i szuka brakujących danych (np. nazwisk).
    """
    raw_text = state["raw_xml"] + "\n" + state["user_query"]
    
    print("\n" + "="*50)
    print("[DEBUG: HYBRID] Krok 1: Wstępna detekcja przez Presidio...")
    
    # 1. Pozyskanie kandydatów z Presidio
    presidio_candidates = get_pii_candidates(raw_text)
    print(f"[DEBUG: HYBRID] Kandydaci z Presidio: {presidio_candidates}")
    
    # 2. Przekazanie do Bielika w celu weryfikacji i rozszerzenia
    try:
        llm = get_local_llm()
        structured_llm = llm.with_structured_output(PIIData)
        
        prompt = PromptTemplate.from_template(
            "Jesteś ekspertem ochrony danych (DPO). Twoim zadaniem jest stworzenie OSTATECZNEJ listy danych PII.\n\n"
            "SYSTEM PRESIDIO WYKRYŁ NASTĘPUJĄCYCH KANDYDATÓW:\n"
            "{candidates}\n\n"
            "TEKST DO ANALIZY:\n"
            "{text}\n\n"
            "TWOJE ZADANIA:\n"
            "1. WERYFIKACJA: Sprawdź, czy kandydaci z Presidio faktycznie są danymi PII w tym kontekście. "
            "Jeśli coś jest nazwą firmy, postacią historyczną lub adresem urzędu – ODRZUĆ TO.\n"
            "2. ODKRYWANIE: Znajdź w tekście dane PII, których Presidio nie wykryło (szczególnie nazwiska, adresy prywatne).\n"
            "3. CZYSZCZENIE: Zwróć same wartości (np. '5210001234'), bez etykiet typu 'NIP:'.\n\n"
            "ZASADY NEGATYWNE (Czego NIE wypisywać):\n"
            "- Nazw firm, urzędów, instytucji.\n"
            "- Postaci historycznych i powszechnie znanych miejsc.\n"
            "- Słów kluczowych: 'NIP', 'PESEL', 'E-mail', 'IBAN', 'REGON'.\n"
        )
        
        chain = prompt | structured_llm
        result = chain.invoke({
            "candidates": ", ".join(presidio_candidates) if presidio_candidates else "Brak",
            "text": raw_text
        })
        
        final_pii = result.detected_strings if result else []
        
    except Exception as e:
        print(f"[Blad] Bielik zawiódł w fazie weryfikacji: {e}")
        # W razie błędu LLM, zwracamy chociaż wyniki z Presidio jako fallback
        final_pii = presidio_candidates

    print(f"[DEBUG: HYBRID] Ostateczne PII po weryfikacji Bielika: {final_pii}")
    print("="*50)
    
    return {
        "detected_pii": list(set([p.strip() for p in final_pii if p.strip()])),
        "error_status": ""
    }

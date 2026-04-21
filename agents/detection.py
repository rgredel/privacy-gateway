from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from state import GraphState
from llm_manager import get_llm
from agents.presidio_engine import get_pii_candidates

# Model danych dla ustrukturyzowanego wyjścia
class PIIData(BaseModel):
    detected_strings: list[str] = Field(description="Lista ciągów znaków (strings) uznanych za PII lub do usunięcia.")

def detection_agent(state: GraphState) -> GraphState:
    """
    Samodzielny agent LLM (LLM-only). 
    Wykorzystuje strategię Professional DPO (V10).
    """
    raw_text = state["raw_xml"] + "\n" + state["user_query"]
    
    try:
        llm = get_llm("llm-only-detection")
        structured_llm = llm.with_structured_output(PIIData)
        
        system_template = (
            "Jesteś Ekspertem DPO (Data Protection Officer). Twoim zadaniem jest detekcja PII osób fizycznych.\n"
            "ZASADY:\n"
            "1. XML: Dane w tagach są zawsze prawdziwe.\n"
            "2. FIRMY: Wyodrębnij nazwy firm, jeśli zawierają nazwiska (np. 'Kancelaria Jana Nowaka').\n"
            "3. MIASTA: Wyodrębnij miasta, jeśli są częścią adresu lub miejsca zamieszkania.\n"
            "4. FLEKSJA: Zachowaj formę z tekstu (np. 'Anny Nowak-Zielińskiej').\n"
            "5. ODRZUĆ: Postacie historyczne (Kopernik) i duże korporacje."
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", "ANALIZUJ TEKST:\n{text}")
        ])
        
        chain = prompt | structured_llm
        res = chain.invoke({"text": raw_text})
        
        return {"raw_pii_strings": res.detected_strings, "error_status": ""}
    except Exception as e:
        return {"raw_pii_strings": [], "error_status": str(e)}

def hybrid_detection_agent(state: GraphState) -> GraphState:
    """
    Agent hybrydowy wykorzystujący strategię PROFESSIONAL_DPO (V10) 
    z modelem Bielik (Local LLM) do weryfikacji kandydatów z Presidio.
    """
    raw_text = state["raw_xml"] + "\n" + state["user_query"]
    presidio_candidates = get_pii_candidates(raw_text)
    
    if not presidio_candidates:
        return {"raw_pii_strings": [], "error_status": ""}

    try:
        # Używamy modelu skonfigurowanego w managerze dla detekcji hybrydowej
        llm = get_llm("hybrid-detection")
        structured_llm = llm.with_structured_output(PIIData)
        
        system_prompt = (
            "Jesteś Ekspertem DPO. Twoim zadaniem jest weryfikacja kandydatów NER.\n"
            "Kandydaci: {candidates}\n\n"
            "ZASADY SELEKCJI:\n"
            "1. ZATWIERDŹ: Osoby prywatne, ich NIP, PESEL i dane kontaktowe.\n"
            "2. JDG: Zatwierdź nazwy firm jednoosobowych (np. 'Kancelaria Jana Nowaka').\n"
            "3. MIASTA: Zatwierdź TYLKO jeśli wskazują miejsce zamieszkania/adres osoby.\n"
            "4. ODRZUĆ: Korporacje, urzędy i postacie historyczne (Kopernik, Chopin).\n"
            "5. ODRZUĆ: Miasta w kontekście ogólnym lub historycznym (np. 'urodził się w Toruniu')."
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "TEKST: {text}")
        ])
        
        chain = prompt | structured_llm
        res = chain.invoke({"text": raw_text, "candidates": ", ".join(presidio_candidates)})
        
        return {"raw_pii_strings": res.detected_strings, "error_status": ""}

    except Exception as e:
        return {"raw_pii_strings": presidio_candidates, "error_status": str(e)}

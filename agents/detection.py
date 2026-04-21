from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
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
    z modelem do weryfikacji kandydatów z Presidio.
    """
    raw_text = state["raw_xml"] + "\n" + state["user_query"]
    presidio_candidates = get_pii_candidates(raw_text)
    
    if not presidio_candidates:
        return {"raw_pii_strings": [], "error_status": ""}

    try:
        llm = get_llm("hybrid-detection")
        structured_llm = llm.with_structured_output(PIIData)
        
        system_prompt = (
            "Jesteś Ekspertem DPO. Twoim zadaniem jest precyzyjna filtracja kandydatów PII.\n"
            "ZASADY SELEKCJI:\n"
            "1. ZACHOWAJ: Imiona, nazwiska, dane kontaktowe, PESEL, NIP (również firm jednoosobowych/JDG), numery kont.\n"
            "2. ADRESY: Zachowaj miasta TYLKO jeśli wskazują adres zamieszkania, biura lub wysyłki osoby fizycznej (np. 'zamieszkały w Lublinie').\n"
            "3. USUŃ: Postacie historyczne i sławne (np. Sienkiewicz, Matejko) oraz miasta w ich kontekście (np. 'urodził się w...', 'muzeum w...').\n"
            "4. USUŃ: Duże korporacje (np. KGHM, Orlen), urzędy i dane testowe (np. same zera).\n"
            "5. KONTEKST: Zawsze analizuj tekst, aby odróżnić dane osoby prywatnej od faktów ogólnych/historycznych.\n\n"
            "PRZYKŁAD:\n"
            "Tekst: 'Paweł Nowakowski z Lublina pisał o Henryku Sienkiewiczu z Woli Okrzejskiej.'\n"
            "Kandydaci: Paweł Nowakowski, Lublina, Henryku Sienkiewiczu, Woli Okrzejskiej\n"
            "Wynik: ['Paweł Nowakowski', 'Lublina']"
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "TEKST: {text}\nKANDYDACI: {candidates}\nZWRÓĆ TYLKO LISTĘ ZATWIERDZONYCH FRAZ:")
        ])
        
        chain = prompt | structured_llm
        res = chain.invoke({"text": raw_text, "candidates": ", ".join(presidio_candidates)})
        
        return {"raw_pii_strings": res.detected_strings, "error_status": ""}

    except Exception as e:
        return {"raw_pii_strings": presidio_candidates, "error_status": str(e)}

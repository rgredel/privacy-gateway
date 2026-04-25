from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from state import GraphState
from llm_manager import get_llm
from agents.presidio_engine import get_pii_candidates

from langchain_text_splitters import RecursiveCharacterTextSplitter

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
        llm = get_llm("llm-only-detection", state=state)
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
        
        # Map-Reduce: Chunking
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        chunks = text_splitter.split_text(raw_text)
        payloads = [{"text": chunk} for chunk in chunks]
        
        # Map-Reduce: Batch Processing
        results = chain.batch(payloads, return_exceptions=True)
        
        # Map-Reduce: Reduce/Aggregation
        aggregated_pii = set()
        for res in results:
            if isinstance(res, Exception): continue
            if res and res.detected_strings:
                for s in res.detected_strings:
                    aggregated_pii.add(s.strip())
        
        return {"raw_pii_strings": list(aggregated_pii), "error_status": ""}
    except Exception as e:
        return {"raw_pii_strings": [], "error_status": str(e)}

def hybrid_detection_agent(state: GraphState) -> GraphState:
    """
    Agent hybrydowy wykorzystujący strategię PROFESSIONAL_DPO (V10) 
    z modelem do weryfikacji kandydatów z Presidio oraz Map-Reduce.
    """
    raw_text = state["raw_xml"] + "\n" + state["user_query"]
    presidio_candidates = get_pii_candidates(raw_text)
    
    if not presidio_candidates:
        return {"raw_pii_strings": [], "error_status": ""}

    try:
        llm = get_llm("hybrid-detection", state=state)
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
        
        # Map-Reduce: Chunking
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)
        chunks = text_splitter.split_text(raw_text)
        
        # Przygotowanie paczek - filtrujemy kandydatów do tych widocznych w chunkach
        payload_list = []
        for chunk in chunks:
            # Szybki filtr kandydatów dla danego kawałka tekstu
            chunk_candidates = [c for c in presidio_candidates if c in chunk]
            payload_list.append({
                "text": chunk, 
                "candidates": ", ".join(chunk_candidates) if chunk_candidates else "Brak"
            })

        # Map-Reduce: Parallel Batch Execution
        results = chain.batch(payload_list, return_exceptions=True)
        
        # Map-Reduce: Aggregation (Reduce)
        aggregated_pii = set()
        for res in results:
            if isinstance(res, Exception):
                continue
            if res and res.detected_strings:
                for s in res.detected_strings:
                    if s.strip():
                        aggregated_pii.add(s.strip())
        
        return {"raw_pii_strings": list(aggregated_pii), "error_status": ""}

    except Exception as e:
        return {"raw_pii_strings": presidio_candidates, "error_status": str(e)}

def ner_only_detection_agent(state: GraphState) -> GraphState:
    """
    Agent wykorzystujący wyłącznie silnik NER (Presidio + spaCy).
    Pomija jakiekolwiek wywołania LLM. Bezpośrednio zwraca labeled_pii_entities.
    """
    raw_text = state["raw_xml"] + "\n" + state["user_query"]
    from agents.presidio_engine import setup_presidio_analyzer
    analyzer = setup_presidio_analyzer()
    
    if not analyzer:
        return {"labeled_pii_entities": [], "error_status": "Błąd inicjalizacji Presidio"}

    try:
        results = analyzer.analyze(text=raw_text, language="pl")
        labeled_entities = []
        for r in results:
            val = raw_text[r.start:r.end]
            if val.strip():
                labeled_entities.append({"value": val.strip(), "label": r.entity_type})
        
        # De-duplikacja
        unique_entities = []
        seen = set()
        for ent in labeled_entities:
            key = (ent["value"], ent["label"])
            if key not in seen:
                unique_entities.append(ent)
                seen.add(key)

        return {"labeled_pii_entities": unique_entities, "error_status": ""}
    except Exception as e:
        return {"labeled_pii_entities": [], "error_status": str(e)}

from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from state import GraphState
from llm_manager import get_llm

class PIIEntity(BaseModel):
    value: str = Field(description="Oryginalna wartość PII z tekstu")
    label: str = Field(description="Etykieta (np. OSOBA, NIP, ADRES)")

class LabelingData(BaseModel):
    entities: list[PIIEntity] = Field(description="Lista sklasyfikowanych encji PII")

def labeling_agent(state: GraphState) -> GraphState:
    """
    Sklasyfikuj podane elementy PII, nadając im typy (semantyczne maskowanie).
    """
    raw_pii_strings = state.get("raw_pii_strings", [])
    if not raw_pii_strings:
        return {"labeled_pii_entities": []}

    print("\n" + "="*50)
    print(f"[DEBUG: LABELING] Klasyfikacja {len(raw_pii_strings)} encji PII...")

    try:
        llm = get_llm("labeling")
        structured_llm = llm.with_structured_output(LabelingData)
        
        prompt = PromptTemplate.from_template(
            "Jesteś DPO (Inspektorem Ochrony Danych). Sklasyfikuj podane elementy PII.\n\n"
            "### KONTEKST:\n"
            "{context}\n\n"
            "### ELEMENTY DO SKLASYFIKOWANIA:\n"
            "{pii_list}\n\n"
            "### DOSTĘPNE ETYKIETY:\n"
            "- OSOBA_KOBIETA, OSOBA_MEZCZYZNA, NIP, PESEL, ADRES, FIRMA, EMAIL, INNE\n"
        )
        
        full_context = state.get("raw_xml", "") + "\n" + state.get("user_query", "")
        chain = prompt | structured_llm
        result = chain.invoke({
            "context": full_context,
            "pii_list": ", ".join(raw_pii_strings)
        })
        
        # Logika dopasowania
        entities = []
        labeled_map = {e.value.strip().lower(): e.label.upper() for e in result.entities}
        
        for pii in raw_pii_strings:
            label = labeled_map.get(pii.strip().lower(), "DANA")
            entities.append({"value": pii, "label": label})
        
        print(f"[DEBUG: LABELING] Wynik: {entities}")
        
    except Exception as e:
        print(f"[DEBUG: LABELING] Błąd: {e}")
        entities = [{"value": p, "label": "DANA"} for p in raw_pii_strings]

    print("="*50)
    return {"labeled_pii_entities": entities}

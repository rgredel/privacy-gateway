from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from state import GraphState
from llm_factory import get_local_llm

class PIIEntity(BaseModel):
    value: str = Field(description="Wartość danej PII")
    label: str = Field(description="Typ danej (np. OSOBA, NIP, PESEL, ADRES, FIRMA, EMAIL)")

class LabelingData(BaseModel):
    entities: list[PIIEntity] = Field(description="Lista sklasyfikowanych encji PII")

import difflib

def labeling_agent(state: GraphState) -> GraphState:
    """
    Nowy węzeł: Klasyfikuje wykryte wcześniej napisy PII, nadając im typy.
    """
    raw_pii_strings = state.get("raw_pii_strings", [])
    if not raw_pii_strings:
        return {"labeled_pii_entities": []}

    print("\n" + "="*50)
    print(f"[DEBUG: LABELING] Klasyfikacja {len(raw_pii_strings)} encji PII...")

    try:
        llm = get_local_llm()
        structured_llm = llm.with_structured_output(LabelingData)
        
        prompt = PromptTemplate.from_template(
            "Jesteś DPO (Inspektorem Ochrony Danych). Sklasyfikuj podane elementy PII.\n\n"
            "### KONTEKST:\n"
            "{context}\n\n"
            "### ELEMENTY DO SKLASYFIKOWANIA:\n"
            "{pii_list}\n\n"
            "### DOSTĘPNE ETYKIETY:\n"
            "- OSOBA_KOBIETA, OSOBA_MEZCZYZNA, NIP, PESEL, ADRES, FIRMA, EMAIL, INNE\n\n"
            "### ZASADY:\n"
            "1. Zwróć JSON z listą obiektów {{\"value\": \"...\", \"label\": \"...\"}}.\n"
            "2. 'value' musi być IDENTYCZNE jak na liście powyżej.\n"
            "3. 'label' musi być jedną z powyższych etykiet.\n\n"
            "### PRZYKŁAD:\n"
            "{{\n"
            "  \"entities\": [\n"
            "    {{\"value\": \"Jan Nowak\", \"label\": \"OSOBA_MEZCZYZNA\"}}\n"
            "  ]\n"
            "}}\n"
        )
        
        full_context = state.get("raw_xml", "") + "\n" + state.get("user_query", "")
        chain = prompt | structured_llm
        result = chain.invoke({
            "context": full_context,
            "pii_list": ", ".join(raw_pii_strings)
        })
        
        print(f"[DEBUG: LABELING] Raw result: {result}")
        
        # Logika dopasowania: Model 1.5b może halucynować wartości z przykładu lub literówki.
        entities = []
        labeled_map = {e.value.strip().lower(): e.label.upper() for e in result.entities}
        llm_values = list(labeled_map.keys())
        
        for pii in raw_pii_strings:
            clean_pii = pii.strip().lower()
            
            # 1. Dokładne dopasowanie
            label = labeled_map.get(clean_pii)
            
            # 2. Fuzzy matching (difflib)
            if not label and llm_values:
                matches = difflib.get_close_matches(clean_pii, llm_values, n=1, cutoff=0.6)
                if matches:
                    label = labeled_map.get(matches[0])
            
            # 3. Fallback
            if not label:
                label = "DANA"
                
            entities.append({"value": pii, "label": label})
        
    except Exception as e:
        print(f"[DEBUG: LABELING] Błąd klasyfikacji: {e}")
        # Fallback: wszystkie jako DANA
        entities = [{"value": p, "label": "DANA"} for p in raw_pii_strings]

    print(f"[DEBUG: LABELING] Wynik: {entities}")
    print("="*50)

    return {"labeled_pii_entities": entities}

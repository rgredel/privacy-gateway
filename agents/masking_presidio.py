import re
from state import GraphState
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from presidio_analyzer import RecognizerResult

def masking_presidio_agent(state: GraphState) -> GraphState:
    """
    Używa modułu transformacji Presidio (AnonymizerEngine) do bezpiecznego maskowania.
    Zaleta: Rozwiązuje problemy z nakładającymi się frazami i zagnieżdżonymi zamianami.
    
    W tej wersji NIE uruchamiamy własnej detekcji Presidio, lecz wykorzystujemy
    dane PII już wykryte i zweryfikowane przez flow (state['labeled_pii_entities']).
    """
    engine = AnonymizerEngine()
    
    raw_context = state["raw_xml"]
    raw_query = state["user_query"]
    entities = state.get("labeled_pii_entities", [])
    
    print("\n" + "-"*30)
    print("[DEBUG: MASKING-PRESIDIO] Transformacja przy użyciu AnonymizerEngine...")
    
    def get_analyzer_results(text, pii_entities):
        results = []
        for idx, ent in enumerate(pii_entities):
            val = ent["value"]
            lbl = ent["label"]
            # Szukamy wszystkich wystąpień wartości w tekście
            for match in re.finditer(re.escape(val), text):
                results.append(RecognizerResult(
                    entity_type=f"{lbl}_{idx}", # Unikalny typ dla każdej encji, by zachować ID
                    start=match.start(),
                    end=match.end(),
                    score=1.0
                ))
        return results

    # Przygotowanie wyników analizy dla kontekstu i zapytania
    context_results = get_analyzer_results(raw_context, entities)
    query_results = get_analyzer_results(raw_query, entities)
    
    print(f"[DEBUG: MASKING-PRESIDIO] Znaleziono {len(context_results)} wystąpień PII w kontekście.")
    print(f"[DEBUG: MASKING-PRESIDIO] Znaleziono {len(query_results)} wystąpień PII w zapytaniu.")
    
    # Definiujemy operatory dla każdej encji, aby uzyskać format [ETYKIETA_ID]
    operators = {}
    for idx, ent in enumerate(entities):
        lbl = ent["label"].upper()
        operators[f"{ent['label']}_{idx}"] = OperatorConfig(
            "replace", 
            {"new_value": f"[{lbl}_{idx}]"}
        )

    # Transformacja kontekstu
    anonymized_context = engine.anonymize(
        text=raw_context,
        analyzer_results=context_results,
        operators=operators
    )
    
    # Transformacja zapytania
    anonymized_query = engine.anonymize(
        text=raw_query,
        analyzer_results=query_results,
        operators=operators
    )
    
    # Budujemy Vault na podstawie pii_entities (zgodnie z formatem systemu)
    vault = {}
    for idx, ent in enumerate(entities):
        token = f"[{ent['label'].upper()}_{idx}]"
        vault[token] = ent["value"]

    print(f"[DEBUG: MASKING-PRESIDIO] Skarbiec (Vault): {vault}")
    print(f"[DEBUG: MASKING-PRESIDIO] Zanonimizowane zapytanie: {anonymized_query.text}")
    print("-"*30)
    
    return {
        "masked_context": anonymized_context.text, 
        "masked_query": anonymized_query.text, 
        "vault": vault
    }

from state import GraphState
from llm_factory import get_prompt_guard_classifier, translate_pl_to_en

# Domyślny próg decyzyjny — zapytania z P(malicious) > THRESHOLD są blokowane
DEFAULT_THRESHOLD = 0.85


def guardrail_agent(state: GraphState) -> GraphState:
    """
    Analiza bezpieczeństwa zapytania użytkownika (Prompt Injection / Jailbreak).
    Pipeline: tłumaczenie PL→EN (opus-mt) → klasyfikacja (PromptGuard-2 86M).
    """
    # Sprawdzenie czy agent jest włączony w ustawieniach UI
    if state.get("enable_guardrail") is False:
        print("[DEBUG: GUARDRAIL] Agent wyłączony w ustawieniach.")
        return {"is_safe": True}

    try:
        classifier = get_prompt_guard_classifier()
        query = state.get("user_query", "")
        threshold = state.get("guardrail_threshold", DEFAULT_THRESHOLD)

        # 1. Tłumaczenie PL → EN (model PromptGuard działa najlepiej na angielskim)
        translated = translate_pl_to_en(query)
        print(f"[DEBUG: GUARDRAIL] Tłumaczenie: '{query[:60]}' → '{translated[:60]}'")

        # 2. Klasyfikacja przetłumaczonego tekstu
        results = classifier(translated)
        top_result = results[0]
        label = top_result["label"]
        score = top_result["score"]

        # Prompt Guard 2 — LABEL_0 = benign, LABEL_1 = malicious
        is_malicious = label == "LABEL_1" and score > threshold
        is_safe = not is_malicious

        print("\n" + "#" * 50)
        print(f"[DEBUG: GUARDRAIL] PromptGuard-2 | "
              f"Wynik: {label} (score={score:.4f}, próg={threshold}) → "
              f"{'✅ BEZPIECZNE' if is_safe else '🛑 ATAK!'}")
        print("#" * 50)

        return {"is_safe": is_safe}

    except Exception as e:
        print(f"[DEBUG: GUARDRAIL] Błąd PromptGuard: {e}")
        return {"is_safe": True}


def check_guardrail(state: GraphState) -> str:
    if state.get("is_safe", True):
        return "cloud_llm"
    return "blocked"

from state import GraphState
from llm_factory import get_prompt_guard_classifier

# Domyślny próg decyzyjny — zapytania z P(injection/jailbreak) > THRESHOLD są blokowane
DEFAULT_THRESHOLD = 0.85


def guardrail_agent(state: GraphState) -> GraphState:
    """
    Analiza bezpieczeństwa zapytania użytkownika (Prompt Injection / Jailbreak).
    Używa dedykowanego modelu klasyfikacyjnego PromptGuard-86M zamiast ogólnego LLM.
    """
    # Sprawdzenie czy agent jest włączony w ustawieniach UI
    if state.get("enable_guardrail") is False:
        print("[DEBUG: GUARDRAIL] Agent wyłączony w ustawieniach.")
        return {"is_safe": True}

    try:
        classifier = get_prompt_guard_classifier()
        query = state.get("user_query", "")
        threshold = state.get("guardrail_threshold", DEFAULT_THRESHOLD)

        # Klasyfikacja — model zwraca etykiety: BENIGN / INJECTION / JAILBREAK
        results = classifier(query)
        # results = [{"label": "BENIGN", "score": 0.99}, ...]
        top_result = results[0]
        label = top_result["label"]
        score = top_result["score"]

        # Prompt Guard 2 — LABEL_0 = benign, LABEL_1 = malicious
        is_malicious = label == "LABEL_1" and score > threshold
        is_safe = not is_malicious

        print("\n" + "#" * 50)
        print(f"[DEBUG: GUARDRAIL] PromptGuard-86M | "
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

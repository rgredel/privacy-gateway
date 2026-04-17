import os
from langchain_core.prompts import PromptTemplate
from state import GraphState
from llm_factory import get_cloud_llm

def cloud_llm(state: GraphState) -> GraphState:
    """
    Wywołanie Google Gemini z zabezpieczonymi danymi.
    """
    if "GOOGLE_API_KEY" not in os.environ:
        return {**state, "cloud_response": "BŁĄD: Brak klucza GOOGLE_API_KEY w zmiennych środowiskowych."}

    llm = get_cloud_llm()
    
def hybrid_detection_agent(state: GraphState) -> GraphState:
    raw_text = state["raw_xml"] + "\n" + state["user_query"]
    presidio_candidates = get_pii_candidates(raw_text)
    
    # DYNAMICZNA INSTRUKCJA (Zwalczanie "leniwego LLM")
    discovery_mode = ""
    if not presidio_candidates:
        discovery_mode = (
            "UWAGA: Skaner Presidio nie znalazł nic. BĄDŹ EKSTREMALNIE CZUJNY. "
            "To Ty jesteś teraz jedyną linią obrony. Przeszukaj tekst bardzo dokładnie."
        )
    else:
        discovery_mode = f"Skaner Presidio wstępnie znalazł: {', '.join(presidio_candidates)}. Zweryfikuj to."

    # PROMPT ZASADY "DON'T FIX, JUST COPY"
    prompt_template = (
        "### ROLA: RYGORYSTYCZNY SKANER PII\n"
        "Twoim jedynym zadaniem jest wyodrębnienie danych PII osób prywatnych.\n\n"
        f"{discovery_mode}\n\n"
        "### ŻELAZNE ZASADY (STRICT CONSTRAINTS):\n"
        "1. ZASADA 1:1 (VERBATIM): Kopiuj dane DOKŁADNIE tak, jak występują w tekście. "
        "Nigdy nie poprawiaj literówek, nie zmieniaj nazwisk (np. Kowalski na Nowak) i nie formatuj danych.\n"
        "2. BEZ ETYKIET: Zwracaj same wartości. Zakaz używania prefiksów typu 'NIP:', 'ul.', 'PESEL:'.\n"
        "3. FILTR JDG: Ignoruj nazwy firm (np. 'Usługi Transportowe Kowalski'). Wypisz tylko imię i nazwisko osoby prywatnej.\n"
        "4. KONTEKST PRYWATNY: Ignoruj postacie historyczne i adresy urzędów (np. Wiejska 4).\n\n"
        "### PRZYKŁADY DO NAŚLADOWANIA:\n"
        "- Tekst: 'Faktura dla Jan Kowalsky' -> Wyjście: ['Jan Kowalsky'] (nie zmieniaj na Kowalski!)\n"
        "- Tekst: 'NIP: 634012' -> Wyjście: ['634012'] (bez słowa NIP)\n\n"
        "TEKST DO ANALIZY:\n{text}"
    )
    
    chain = prompt | llm
    
    # Logowanie zanonimizowanego promptu
    formatted_prompt = prompt.format(
        context=state["masked_context"],
        query=state["masked_query"]
    )
    print("\n" + "☁️"*20)
    print("[DEBUG: CLOUD] Wysyłanie zanonimizowanego zapytania do Gemini...")
    # print(f"[DEBUG: CLOUD] Pełny Prompt:\n{formatted_prompt}") # Opcjonalnie (może być bardzo długie)
    print(f"[DEBUG: CLOUD] Zanonimizowane pytanie: {state['masked_query']}")
    
    # Wywołanie z zanonimizowanym kontekstem i zapytaniem
    result = chain.invoke({
        "context": state["masked_context"],
        "query": state["masked_query"]
    })
    
    print(f"[DEBUG: CLOUD] Surowa odpowiedź (z tokenami): {result.content}")
    print("☁️"*20)
    
    return {"cloud_response": result.content}

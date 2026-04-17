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
    
    prompt = PromptTemplate.from_template(
        "Jesteś uprzejmym i wysoce wykwalifikowanym asystentem biznesowo-finansowym. "
        "Twoim zadaniem jest odpowiadanie na polecenia i pytania w sposób inteligentny, konwersacyjny i naturalny.\n\n"
        "Podczas formułowania odpowiedzi powinieneś przeanalizować podany poniżej kontekst. "
        "Pamiętaj, że otrzymane od systemu dane RAG (kontekst) będą w dużej mierze pochodzić ze zrzutów z "
        "systemu Comarch ERP Optima (księgowość, kadry, faktury, baza kontrahentów itp.).\n"
        "Zależy mi, abyś łączył te firmowe dane i dopowiadał je ze swoją szeroką wiedzą nabytą z internetu o prawie i księgowości. "
        "Nie opieraj się w 100% wyłącznie na kontekście - użyj go jako inspiracji lub weryfikacji, "
        "ale śmiało dopełniaj luki swoimi faktami, informacjami i wyciągaj obszerne wnioski analityczne.\n\n"
        "WAŻNE (ZASADY MASKOWANIA PII):\n"
        "Zarówno dostarczony kontekst, jak i pytanie użytkownika, zostały zanonimizowane - "
        "dane wrażliwe ukryto pod identyfikatorami w nawiasach kwadratowych, np. [PII_0], [PII_1].\n"
        "To absolutnie kluczowe: Budując ostateczną odpowiedź, dla każdego chronionego podmiotu MUSISZ użyć tych samych indeksów w wygenerowanym zdaniu (np. 'Zgodnie z fakturą dla [PII_0]...'). Zostaną one potem automatycznie odszyfrowane przez mój system z powrotem. Nigdy pod żadnym pozorem nie zmyślaj prawdziwych nazw z internetu w miejsce ukrytych klamr.\n\n"
        "KONTEKST Z ERP OPTIMA:\n{context}\n\n"
        "PYTANIE UŻYTKOWNIKA:\n{query}"
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

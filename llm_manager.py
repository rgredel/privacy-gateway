from llm_factory import get_local_model, get_cloud_gemini_2_5_flash

# Słownik mapujący klucze usług na konkretne funkcje fabrykujące LLM
LLM_CONFIG = {
    "hybrid-detection": get_local_model,
    "llm-only-detection": get_local_model,
    "labeling": get_local_model,
    "guardrail": get_local_model,
    "main-cloud-llm": get_cloud_gemini_2_5_flash
}

def get_llm(service_name: str, state=None, **kwargs):
    """
    Zwraca instancję modelu LLM dla danej usługi.
    Pobiera konfigurację modelu ze stanu (state), jeśli jest dostępny.
    Wybiera odpowiednią fabrykę (lokalną lub chmurową) na podstawie nazwy modelu.
    """
    # 1. Pobranie nazwy modelu
    if state:
        if service_name == "main-cloud-llm":
            model_name = state.get("cloud_model", "gemini-2.5-flash")
        else:
            # Dla usług przetwarzania wewnętrznego (detekcja, etykietowanie, guardrail)
            model_name = state.get("local_model", "qooba/bielik-1.5b-v3.0-instruct:Q8_0")
        kwargs["model_name"] = model_name
    else:
        model_name = kwargs.get("model_name", "")

    # 2. Wybór odpowiedniej fabryki na podstawie nazwy modelu
    # Jeśli nazwa zawiera "gemini", używamy fabryki chmurowej, w przeciwnym razie lokalnej (Ollama)
    if "gemini" in model_name.lower():
        factory_func = get_cloud_gemini_2_5_flash
    else:
        factory_func = get_local_model
            
    return factory_func(**kwargs)

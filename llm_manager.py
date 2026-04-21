from llm_factory import get_local_bielik_1_5, get_cloud_gemini_2_5_flash

# Słownik mapujący klucze usług na konkretne funkcje fabrykujące LLM
LLM_CONFIG = {
    "hybrid-detection": get_local_bielik_1_5,
    "llm-only-detection": get_local_bielik_1_5,
    "labeling": get_local_bielik_1_5,
    "guardrail": get_local_bielik_1_5,
    "main-cloud-llm": get_cloud_gemini_2_5_flash
}

def get_llm(service_name: str, **kwargs):
    """
    Zwraca instancję modelu LLM dla danej usługi.
    Przekazuje dodatkowe parametry (np. format, temperature) do fabryki.
    """
    factory_func = LLM_CONFIG.get(service_name)
    if not factory_func:
        raise ValueError(f"Nieznana usługa LLM: {service_name}")
    
    return factory_func(**kwargs)

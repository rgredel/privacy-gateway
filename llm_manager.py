from llm_factory import get_local_bielik_1_5, get_cloud_gemini_2_5_flash

# Słownik mapujący klucze usług na konkretne funkcje fabrykujące LLM
LLM_CONFIG = {
    "hybrid-detection": get_local_bielik_1_5,
    "llm-only-detection": get_cloud_gemini_2_5_flash,
    "labeling": get_local_bielik_1_5,
    "guardrail": get_local_bielik_1_5,
    "main-cloud-llm": get_cloud_gemini_2_5_flash
}

def get_llm(service_key: str):
    """
    Zwraca instancję LLM skonfigurowaną dla danej usługi.
    
    Args:
        service_key (str): Klucz usługi (np. 'hybrid-detection', 'labeling')
        
    Returns:
        BaseChatModel: Instancja modelu LangChain
    """
    factory_func = LLM_CONFIG.get(service_key)
    if not factory_func:
        raise ValueError(f"Nieznany klucz usługi LLM: {service_key}. Dostępne: {list(LLM_CONFIG.keys())}")
    
    return factory_func()

import os
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from src.app.core.config import settings

def get_local_model(model_name: str = None, temperature: float = 0.0, format: str = None) -> ChatOllama:
    """Zwraca lokalny model (Ollama)."""
    if model_name is None:
        model_name = settings.local_model_default
        
    return ChatOllama(
        model=model_name, 
        temperature=temperature,
        format=format,
        base_url=settings.ollama_base_url
    )

def get_cloud_gemini_2_5_flash(temperature: float = 0.0, model_name: str = None, **kwargs) -> ChatGoogleGenerativeAI:
    """Zwraca model chmurowy Gemini."""
    if model_name is None:
        model_name = settings.cloud_model_default
        
    return ChatGoogleGenerativeAI(
        model=model_name, 
        temperature=temperature,
        google_api_key=settings.google_api_key
    )

# --- Prompt Guard Classifier (Singleton) ---
_prompt_guard_classifier = None

def get_prompt_guard_classifier():
    """Zwraca singleton klasyfikatora PromptGuard."""
    global _prompt_guard_classifier
    if _prompt_guard_classifier is None:
        from transformers import pipeline as hf_pipeline
        hf_token = settings.hf_token
        print("[DEBUG: FACTORY] Ładowanie modelu Llama-Prompt-Guard-2-86M...")
        _prompt_guard_classifier = hf_pipeline(
            "text-classification",
            model="meta-llama/Llama-Prompt-Guard-2-86M",
            token=hf_token,
        )
        print("[DEBUG: FACTORY] Model Llama-Prompt-Guard-2-86M załadowany.")
    return _prompt_guard_classifier

def translate_pl_to_en(text: str) -> str:
    """Tłumaczy tekst z polskiego na angielski."""
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="pl", target="en").translate(text)

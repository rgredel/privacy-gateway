import os
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

def get_local_model(model_name: str = "qooba/bielik-1.5b-v3.0-instruct:Q8_0", temperature: float = 0.0, format: str = None) -> ChatOllama:
    """Zwraca lokalny model (Ollama)."""
    return ChatOllama(
        model=model_name, 
        temperature=temperature,
        format=format
    )

def get_cloud_gemini_2_5_flash(temperature: float = 0.0, model_name: str = "gemini-2.5-flash", **kwargs) -> ChatGoogleGenerativeAI:
    """Zwraca model chmurowy Gemini (domyślnie 2.5 Flash)."""
    return ChatGoogleGenerativeAI(model=model_name, temperature=temperature)


# --- Prompt Guard Classifier (Singleton) ---
_prompt_guard_classifier = None

def get_prompt_guard_classifier():
    """
    Zwraca singleton klasyfikatora do detekcji Prompt Injection.
    Model: meta-llama/Llama-Prompt-Guard-2-86M (~86M params, mDeBERTa, wielojęzyczny).
    Klasyfikacja binarna: BENIGN / MALICIOUS.
    Wymaga HF_TOKEN w .env (model gated — jednorazowa akceptacja licencji na HF).
    """
    global _prompt_guard_classifier
    if _prompt_guard_classifier is None:
        from transformers import pipeline as hf_pipeline
        hf_token = os.environ.get("HF_TOKEN")
        print("[DEBUG: FACTORY] Ładowanie modelu Llama-Prompt-Guard-2-86M...")
        _prompt_guard_classifier = hf_pipeline(
            "text-classification",
            model="meta-llama/Llama-Prompt-Guard-2-86M",
            token=hf_token,
        )
        print("[DEBUG: FACTORY] Model Llama-Prompt-Guard-2-86M załadowany.")
    return _prompt_guard_classifier

def translate_pl_to_en(text: str) -> str:
    """
    Tłumaczy tekst z polskiego na angielski.
    Używa Google Translate (deep-translator) — lekki, bez modeli lokalnych.
    """
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="pl", target="en").translate(text)

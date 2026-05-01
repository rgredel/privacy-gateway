import os
from typing import Any, Optional
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from src.app.core.config import settings

def get_local_model(model_name: Optional[str] = None, temperature: float = 0.0, format: Optional[str] = None) -> ChatOllama:
    """Returns a local LLM instance via Ollama.
    
    Args:
        model_name (Optional[str]): The identifier of the Ollama model. Defaults to settings.
        temperature (float): Sampling temperature. Defaults to 0.0.
        format (Optional[str]): Expected output format (e.g., 'json').
        
    Returns:
        ChatOllama: An initialized LangChain Ollama model instance.
    """
    if model_name is None:
        model_name = settings.local_model_default
        
    return ChatOllama(
        model=model_name, 
        temperature=temperature,
        format=format,
        base_url=settings.ollama_base_url
    )

def get_cloud_gemini_2_5_flash(temperature: float = 0.0, model_name: Optional[str] = None, **kwargs: Any) -> ChatGoogleGenerativeAI:
    """Returns a cloud-based Gemini LLM instance.
    
    Args:
        temperature (float): Sampling temperature. Defaults to 0.0.
        model_name (Optional[str]): Specific Gemini model version. Defaults to settings.
        **kwargs: Additional provider-specific parameters.
        
    Returns:
        ChatGoogleGenerativeAI: An initialized Gemini model instance.
    """
    if model_name is None:
        model_name = settings.cloud_model_default
        
    return ChatGoogleGenerativeAI(
        model=model_name, 
        temperature=temperature,
        google_api_key=settings.google_api_key
    )

def get_model(model_name: str, temperature: float = 0.0, **kwargs: Any) -> Any:
    """Dynamic factory that routes to either Ollama or Gemini based on the model name.
    
    This function acts as a central router for dynamic model selection in the infrastructure.
    
    Args:
        model_name (str): The full identifier of the model.
        temperature (float): Sampling temperature.
        **kwargs: Additional arguments passed to the specific model constructor.
        
    Returns:
        Any: A LangChain-compatible LLM instance (ChatOllama or ChatGoogleGenerativeAI).
    """
    if "gemini" in model_name.lower():
        return get_cloud_gemini_2_5_flash(model_name=model_name, temperature=temperature, **kwargs)
    else:
        return get_local_model(model_name=model_name, temperature=temperature, **kwargs)

# --- Prompt Guard Classifier (Singleton) ---
_prompt_guard_classifier: Optional[Any] = None

def get_prompt_guard_classifier() -> Any:
    """Returns a singleton instance of the PromptGuard classifier.
    
    Loads the Llama-Prompt-Guard-2-86M model from HuggingFace on first call.
    
    Returns:
        Any: A transformers pipeline for text-classification.
    """
    global _prompt_guard_classifier
    if _prompt_guard_classifier is None:
        from transformers import pipeline as hf_pipeline
        hf_token = settings.hf_token
        print("[DEBUG: FACTORY] Loading Llama-Prompt-Guard-2-86M model...")
        _prompt_guard_classifier = hf_pipeline(
            "text-classification",
            model="meta-llama/Llama-Prompt-Guard-2-86M",
            token=hf_token,
        )
        print("[DEBUG: FACTORY] Model Llama-Prompt-Guard-2-86M loaded.")
    return _prompt_guard_classifier

def translate_pl_to_en(text: str) -> str:
    """Translates text from Polish to English using Google Translator.
    
    Used as a pre-processing step for PromptGuard which performs better on English.
    
    Args:
        text (str): Original text in Polish.
        
    Returns:
        str: Translated text in English.
    """
    from deep_translator import GoogleTranslator
    return str(GoogleTranslator(source="pl", target="en").translate(text))

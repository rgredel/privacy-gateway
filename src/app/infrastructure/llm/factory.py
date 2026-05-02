import os
from typing import Any, Optional, List
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.llms import Replicate
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

class ReplicateBielik(Replicate):
    """Custom adapter for Bielik models on Replicate that require 'input' key instead of 'prompt'."""
    def _create_prediction(self, prompt: str, **kwargs: Any) -> Any:
        import replicate as replicate_python
        
        # Merge all inputs. Bielik 11B expects the prompt in the 'input' field.
        all_inputs = {
            "input": prompt,
            **self.model_kwargs,
            **kwargs
        }
        
        # Extract version hash from owner/model:hash string
        version_str = self.model.split(":")[1] if ":" in self.model else None
        
        # Ensure we use the correct token for this specific call
        client = replicate_python.Client(api_token=self.replicate_api_token)
        
        print(f"[DEBUG: REPLICATE] Starting prediction for {self.model}...")
        # Create prediction - this returns immediately, LangChain will call .wait() later
        return client.predictions.create(
            version=version_str,
            input=all_inputs
        )

def get_replicate_model(model_name: str, temperature: float = 0.0, **kwargs: Any) -> Replicate:
    """Returns an LLM instance hosted on Replicate.
    
    Args:
        model_name (str): The identifier of the Replicate model (owner/model).
        temperature (float): Sampling temperature.
        **kwargs: Additional parameters passed to the model.
        
    Returns:
        Replicate: An initialized Replicate LLM instance.
    """
    if not settings.replicate_api_token or "your_token_here" in settings.replicate_api_token:
        raise ValueError("REPLICATE_API_TOKEN is missing or not configured in .env file.")
    
    # Replicate Bielik 11B requires the prompt to be in the "input" field
    # and temperature >= 0.01. It also uses "max_length" instead of max_new_tokens.
    safe_temp = max(0.01, temperature)
    
    return ReplicateBielik(
        model=model_name,
        model_kwargs={
            "temperature": safe_temp,
            "max_length": kwargs.get("max_tokens", 1024),
            "repetition_penalty": 1.1,
            **kwargs
        },
        replicate_api_token=settings.replicate_api_token
    )

def get_model(model_name: str, temperature: float = 0.0, **kwargs: Any) -> Any:
    """Dynamic factory that routes to either Ollama, Gemini, or Replicate based on the model name.
    
    This function acts as a central router for dynamic model selection in the infrastructure.
    
    Args:
        model_name (str): The full identifier of the model.
        temperature (float): Sampling temperature.
        **kwargs: Additional arguments passed to the specific model constructor.
        
    Returns:
        Any: A LangChain-compatible LLM instance.
    """
    if "gemini" in model_name.lower():
        return get_cloud_gemini_2_5_flash(model_name=model_name, temperature=temperature, **kwargs)
    elif "/" in model_name and not model_name.startswith("http"):
        # Pattern owner/model typically indicates a Replicate model
        return get_replicate_model(model_name=model_name, temperature=temperature, **kwargs)
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

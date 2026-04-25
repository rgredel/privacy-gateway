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

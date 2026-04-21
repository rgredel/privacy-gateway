from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI

def get_local_bielik_1_5(temperature: float = 0.0) -> ChatOllama:
    """Zwraca lokalny model Bielik 1.5B (Ollama)."""
    return ChatOllama(model="qooba/bielik-1.5b-v3.0-instruct:Q8_0", temperature=temperature)

def get_cloud_gemini_2_5_flash() -> ChatGoogleGenerativeAI:
    """Zwraca model chmurowy Gemini 2.5 Flash."""
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash")

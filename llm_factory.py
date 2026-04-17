from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI

def get_local_llm(temperature: float = 0.0) -> ChatOllama:
    return ChatOllama(model="qooba/bielik-1.5b-v3.0-instruct:Q8_0", temperature=temperature)

def get_cloud_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash")

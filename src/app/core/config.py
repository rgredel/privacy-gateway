import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application configuration using Pydantic Settings.
    Loads variables from environment or .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Keys
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    hf_token: Optional[str] = os.getenv("HF_TOKEN")

    # LangChain / LangGraph
    langsmith_tracing: bool = False
    langchain_project: str = "privacy-gateway"

    # Default Models
    cloud_model_default: str = "gemini-2.5-flash"
    local_model_default: str = "qooba/bielik-1.5b-v3.0-instruct:Q8_0"
    ollama_base_url: str = "http://localhost:11434"

    # Security
    default_guardrail_threshold: float = 0.85

settings = Settings()

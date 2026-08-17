from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # App
    APP_NAME: str = "TenderFlow MVP"
    APP_VERSION: str = "4.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://tenderflow:tenderflow123@localhost:5432/tenderflow_db"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"

    # Agent settings
    AGENT_TIMEOUT: int = 300
    AGENT_MAX_RETRIES: int = 3
    AGENT_RETRY_WAIT: int = 5

    # Security
    API_KEY: str
    ALLOWED_ORIGINS: List[str] = ["http://localhost:8000", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# Flowise
FLOWISE_BASE_URL: str = "http://localhost:3000"
FLOWISE_AGENT_INTAKE: str = ""
FLOWISE_AGENT_OCR: str = ""
FLOWISE_AGENT_GONOGO: str = ""
FLOWISE_AGENT_COMPLIANCE: str = ""
FLOWISE_AGENT_PRICING: str = ""
FLOWISE_AGENT_PROPOSAL: str = ""
FLOWISE_AGENT_TRACKING: str = ""
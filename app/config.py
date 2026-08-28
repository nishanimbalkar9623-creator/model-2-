"""Application configuration for the AOS AI Engine.

Uses pydantic-settings so everything can be overridden via environment
variables or a local ``.env`` file. No secrets are hardcoded here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Service ----
    service_name: str = "AOS-AI-Engine"
    app_env: Literal["development", "testing", "production"] = "development"
    debug: bool = True
    log_level: str = "DEBUG"

    # ---- LLM provider selection ----
    llm_provider: Literal["mock", "openai", "gemini", "anthropic", "ollama", "openrouter"] = "mock"
    llm_model: Optional[str] = None

    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_base_url: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"

    # ---- OpenRouter ----
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_fast_model: Optional[str] = None
    openrouter_reasoning_model: Optional[str] = None
    openrouter_http_referer: Optional[str] = None
    openrouter_app_name: str = "AOS"
    openrouter_key_cooldown_seconds: float = 60.0
    openrouter_connect_timeout_seconds: float = 10.0
    openrouter_read_timeout_seconds: float = 120.0
    openrouter_request_id_header: str = "X-Request-Id"
    max_llm_retries: int = 3

    # ---- Backend integration ----
    backend_base_url: str = "http://localhost:8000"
    backend_api_key: Optional[str] = None
    backend_jwt_token: Optional[str] = None
    backend_timeout_seconds: float = 15.0
    backend_max_retries: int = 2

    # ---- Memory ----
    memory_ttl_seconds: int = 3600
    memory_max_messages: int = 50

    # ---- RAG ----
    rag_vector_store: Literal["in_memory", "chroma", "faiss"] = "in_memory"
    rag_embedding_provider: str = "mock"
    rag_embedding_model: Optional[str] = None
    rag_top_k: int = 5

    # ---- Speech-to-text ----
    stt_provider: Literal["mock", "openai", "gemini", "whisper-local"] = "mock"
    stt_model: Optional[str] = None

    # ---- Safety ----
    require_confirmation_default: bool = True
    max_request_chars: int = 8000
    max_tools_per_turn: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

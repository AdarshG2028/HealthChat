"""Application settings. Provider selection lives here and nowhere else."""

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderName(StrEnum):
    MOCK = "mock"
    GROQ = "groq"


class JevProviderName(StrEnum):
    MOCK = "mock"
    REAL = "real"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://health:health@localhost:5432/health"

    llm_provider: LLMProviderName = LLMProviderName.MOCK
    groq_api_key: SecretStr | None = None
    llm_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 20.0

    jev_provider: JevProviderName = JevProviderName.MOCK
    typesafe_api_key: SecretStr | None = None
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = 15.0

    # Fault injection for the mock providers (exercise error UIs without real APIs).
    mock_llm_fail_mode: Literal["none", "timeout", "error", "rate_limit", "daily_quota", "invalid", "explain_error"] = (
        "none"
    )
    mock_jev_fail_mode: Literal["none", "timeout", "error", "invalid"] = "none"

    max_turns: int = 8
    max_ask_more_rounds: int = 1
    max_reevaluations: int = 1
    confidence_escalation_threshold: float = 0.6
    human_review_threshold: float = 0.5

    # Public-demo limits; only enforced while a real provider is enabled.
    # Groq free tier: ~200K tokens/day on gpt-oss (verify in your console) ~= 20-30 conversations.
    daily_conversation_cap: int = 25
    daily_jev_call_cap: int = 300
    conversations_per_ip_per_hour: int = 3
    ip_hash_salt: SecretStr = SecretStr("dev-only-salt")

    cors_origins: list[str] = ["http://localhost:3100"]

    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "health-backend"
    log_level: str = "INFO"

    @property
    def uses_real_providers(self) -> bool:
        return self.llm_provider != LLMProviderName.MOCK or self.jev_provider != JevProviderName.MOCK


@lru_cache
def get_settings() -> Settings:
    return Settings()

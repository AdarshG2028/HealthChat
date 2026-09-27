"""The single place where providers are selected. The rest of the app sees only protocols."""

from app.config import JevProviderName, LLMProviderName, Settings
from app.jev.mock_provider import MockJevDecisionProvider
from app.jev.types import JevDecisionProvider
from app.llm.mock_provider import MockLLMProvider
from app.llm.types import LLMProvider


class ProviderConfigError(RuntimeError):
    pass


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == LLMProviderName.MOCK:
        return MockLLMProvider(settings.mock_llm_fail_mode)
    if settings.groq_api_key is None:
        raise ProviderConfigError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
    from app.llm.groq_provider import GroqLLMProvider

    return GroqLLMProvider(
        api_key=settings.groq_api_key.get_secret_value(),
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def build_jev_provider(settings: Settings) -> JevDecisionProvider:
    if settings.jev_provider == JevProviderName.MOCK:
        return MockJevDecisionProvider(settings.mock_jev_fail_mode)
    if settings.typesafe_api_key is None:
        raise ProviderConfigError("TYPESAFE_API_KEY is required when JEV_PROVIDER=real")
    from app.jev.real_provider import RealJevDecisionProvider

    return RealJevDecisionProvider(
        api_key=settings.typesafe_api_key.get_secret_value(),
        model=settings.jev_model,
        timeout_seconds=settings.jev_timeout_seconds,
    )

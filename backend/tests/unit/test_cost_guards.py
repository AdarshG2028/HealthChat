"""Cost protection is enforced mechanically, not by convention."""

import httpx
import pytest
from pydantic import SecretStr
from pytest_socket import SocketBlockedError

from app.config import JevProviderName, LLMProviderName, Settings
from app.domain.patient_state import PatientState
from app.jev.mock_provider import MockJevDecisionProvider
from app.llm.mock_provider import MockLLMProvider
from app.providers import ProviderConfigError, build_jev_provider, build_llm_provider
from tests.conftest import NetworkBlockedError


async def test_outbound_network_is_blocked_in_tests() -> None:
    with pytest.raises((NetworkBlockedError, SocketBlockedError)):
        async with httpx.AsyncClient() as client:
            await client.get("https://api.groq.com")


async def test_real_sdk_clients_cannot_reach_the_network_in_tests() -> None:
    """Even a real provider constructed by mistake cannot spend credits during tests."""
    from app.jev.real_provider import RealJevDecisionProvider
    from app.jev.types import JevCaseInput, JevUnavailableError
    from app.llm.groq_provider import GroqLLMProvider
    from app.llm.types import LLMUnavailableError, TurnContext

    jev = RealJevDecisionProvider(api_key="k", model="jev-latest", timeout_seconds=2)
    with pytest.raises((NetworkBlockedError, SocketBlockedError, JevUnavailableError)) as jev_exc:
        await jev.evaluate_case(JevCaseInput(patient_state=PatientState(), turn_count=1))
    assert _blocked(jev_exc.value), "the Jev request must be stopped by the guard, not by the server"

    llm = GroqLLMProvider(api_key="k", model="m", timeout_seconds=2)
    with pytest.raises((NetworkBlockedError, SocketBlockedError, LLMUnavailableError)) as llm_exc:
        await llm.extract_turn(
            TurnContext(patient_state=PatientState(), recent_messages=[], user_message="hi", turn=1, max_turns=8)
        )
    assert _blocked(llm_exc.value), "the Groq request must be stopped by the guard, not by the server"


def _blocked(exc: BaseException | None) -> bool:
    """True if a network guard error is anywhere in the exception chain."""
    while exc is not None:
        if isinstance(exc, (NetworkBlockedError, SocketBlockedError)):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def test_default_settings_use_mocks() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_provider == LLMProviderName.MOCK
    assert settings.jev_provider == JevProviderName.MOCK
    assert not settings.uses_real_providers
    assert isinstance(build_llm_provider(settings), MockLLMProvider)
    assert isinstance(build_jev_provider(settings), MockJevDecisionProvider)


def test_real_providers_refuse_to_start_without_keys() -> None:
    settings = Settings(_env_file=None, llm_provider="groq", jev_provider="real")  # type: ignore[call-arg]
    with pytest.raises(ProviderConfigError):
        build_llm_provider(settings)
    with pytest.raises(ProviderConfigError):
        build_jev_provider(settings)


def test_real_providers_are_only_built_when_selected() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_provider="groq",
        groq_api_key=SecretStr("k"),
        jev_provider="real",
        typesafe_api_key=SecretStr("k"),
    )
    assert type(build_llm_provider(settings)).__name__ == "GroqLLMProvider"
    assert type(build_jev_provider(settings)).__name__ == "RealJevDecisionProvider"
    assert settings.uses_real_providers

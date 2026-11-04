import subprocess

import pytest

from jobadvaisor import settings as settings_module
from jobadvaisor.settings import Settings, keychain_value


def keychain(monkeypatch, items: dict[str, str]):
    monkeypatch.setattr(settings_module, "keychain_value", items.get)


def test_keychain_secret_beats_the_environment(monkeypatch):
    keychain(monkeypatch, {"llm-api-key": "from-keychain"})
    monkeypatch.setenv("LLM_API_KEY", "from-env")
    assert Settings(_env_file=None).llm_api_key == "from-keychain"


def test_environment_fills_a_secret_missing_from_the_keychain(monkeypatch):
    keychain(monkeypatch, {})
    monkeypatch.setenv("MISTRAL_API_KEY", "from-env")
    assert Settings(_env_file=None).mistral_api_key == "from-env"


def test_explicit_value_beats_the_keychain(monkeypatch):
    keychain(monkeypatch, {"llm-api-key": "from-keychain"})
    assert Settings(_env_file=None, llm_api_key="explicit").llm_api_key == "explicit"


def test_the_old_langfuse_host_name_still_sets_the_base_url(monkeypatch):
    keychain(monkeypatch, {})
    monkeypatch.setenv("LANGFUSE_HOST", "https://old.example")
    assert Settings(_env_file=None).langfuse_base_url == "https://old.example"
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://new.example")
    assert Settings(_env_file=None).langfuse_base_url == "https://new.example"


def test_keychain_is_asked_for_secrets_only(monkeypatch):
    asked = []
    monkeypatch.setattr(settings_module, "keychain_value", asked.append)
    Settings(_env_file=None)
    assert asked == ["llm-api-key", "mistral-api-key", "search-api-key", "langfuse-secret-key"]


@pytest.mark.parametrize("outcome", [FileNotFoundError("security"),
                                     subprocess.CompletedProcess([], 44, "", "not found")])
def test_keychain_value_is_none_without_security_or_item(monkeypatch, outcome):
    def run(*args, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(subprocess, "run", run)
    assert keychain_value("llm-api-key") is None


def test_keychain_value_reads_service_jobadvaisor_and_strips_the_newline(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "secret\n", "")
    monkeypatch.setattr(subprocess, "run", run)
    assert keychain_value("llm-api-key") == "secret"
    assert calls == [["security", "find-generic-password", "-s", "jobadvaisor",
                      "-a", "llm-api-key", "-w"]]

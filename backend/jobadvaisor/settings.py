"""Application settings. Every environment variable the app reads is a field here.

`.env.example` must list exactly these fields, upper-cased; `tests/test_env_example.py` enforces it.
"""

import subprocess
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
KEYCHAIN_SERVICE = "jobadvaisor"
SECRETS = ("llm_api_key", "mistral_api_key", "search_api_key", "langfuse_secret_key")


def keychain_value(account: str) -> str | None:
    """The macOS Keychain password of service `jobadvaisor` and `account`, or `None` when the
    item is missing, the Keychain refuses (locked, denied) or `security` does not exist (Linux,
    CI). Reads silently: an item stored with `security add-generic-password` trusts `security`."""
    try:
        found = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
                                "-a", account, "-w"], capture_output=True, text=True)
    except OSError:
        return None
    return (found.stdout.rstrip("\n") or None) if found.returncode == 0 else None


def keychain_secrets() -> dict[str, str]:
    """Every secret field the Keychain holds, under account = field name with dashes."""
    return {field: value for field in SECRETS
            if (value := keychain_value(field.replace("_", "-")))}


class Settings(BaseSettings):
    """Configuration read from the Keychain, the environment, `.env` and `local.env`.

    Precedence: explicit arguments, then the macOS Keychain (the secrets in `SECRETS` only,
    service `jobadvaisor`; project-scoped, so it beats a same-named variable another project
    exported), then the process environment, then `.env` (secrets where no Keychain exists),
    then `local.env` (non-secret choices such as models and URLs). Both files are gitignored.
    `<role>_model` / `<role>_base_url` override `llm_model` / `llm_base_url` for one role.
    Unset optional values are `None`; tracing stays off without its keys. `search_api_key` is
    reserved for a web-search provider, which no tool uses yet (issue #3).
    `competitor_min_labels` is the training-label minimum of the logistic-regression eval.
    `langfuse_base_url` also reads the earlier name `LANGFUSE_HOST`; `LANGFUSE_BASE_URL` wins.
    `state_directory` holds the rebuildable local stores, outside this repository by default.
    """

    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / "local.env", REPOSITORY_ROOT / ".env"),
        env_ignore_empty=True, extra="ignore",
    )

    data_repository: Path | None = None
    state_directory: Path = Path.home() / ".jobadvaisor"

    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    extractor_model: str | None = None
    extractor_base_url: str | None = None
    judge_model: str | None = None
    judge_base_url: str | None = None
    intake_model: str | None = None
    intake_base_url: str | None = None
    agent_model: str | None = None
    agent_base_url: str | None = None
    embedding_model: str | None = None
    guard_model: str | None = None
    guard_base_url: str | None = None

    mistral_api_key: str | None = None
    guard_thresholds: dict[str, float] | None = None

    search_api_key: str | None = None
    ba_live_test: bool = False
    competitor_min_labels: int = 100

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = Field(
        default=None, validation_alias=AliasChoices("langfuse_base_url", "langfuse_host"))

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        """Insert the Keychain between explicit arguments and the environment."""
        return (init_settings, keychain_secrets, env_settings, dotenv_settings,
                file_secret_settings)

    @field_validator("guard_thresholds")
    @classmethod
    def thresholds_can_flag(cls, thresholds: dict[str, float] | None) -> dict[str, float] | None:
        """Reject an empty set, which would screen without ever flagging, and values outside
        0–1. A value replaces the classifier's defaults; it is not merged with them. `None`
        keeps the defaults."""
        if thresholds is None:
            return None
        if not thresholds:
            raise ValueError("GUARD_THRESHOLDS must name at least one category")
        if outside := sorted(name for name, value in thresholds.items() if not 0 <= value <= 1):
            raise ValueError(f"GUARD_THRESHOLDS must lie between 0 and 1: {', '.join(outside)}")
        return thresholds

    @field_validator("data_repository", "state_directory")
    @classmethod
    def expand_home(cls, path: Path | None) -> Path | None:
        """Expand a leading `~`, which `.env` values do not get from a shell."""
        return path.expanduser() if path else path

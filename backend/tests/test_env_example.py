from pathlib import Path

from jobadvaisor.settings import Settings

ENV_EXAMPLE = Path(__file__).parents[2] / ".env.example"


def env_example_entries() -> dict[str, str]:
    """Return KEY → value for every non-comment, non-blank line of `.env.example`."""
    entries = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            entries[key.strip()] = value.strip()
    return entries


def test_env_example_lists_exactly_the_settings_fields():
    fields = {name.upper() for name in Settings.model_fields}
    assert set(env_example_entries()) == fields


def test_env_example_has_no_values():
    assert {key: value for key, value in env_example_entries().items() if value} == {}


def test_unfilled_copy_of_env_example_loads_as_defaults(tmp_path, monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(ENV_EXAMPLE.read_text())
    assert Settings(_env_file=env_file) == Settings(_env_file=None)


def test_env_overrides_local_env(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    files = [tmp_path / Path(path).name for path in Settings.model_config["env_file"]]
    contents = {"local.env": "LLM_MODEL=local\nLLM_BASE_URL=https://local\n",
                ".env": "LLM_MODEL=secret-file\n"}
    for file in files:
        file.write_text(contents[file.name])
    settings = Settings(_env_file=files)
    assert (settings.llm_model, settings.llm_base_url) == ("secret-file", "https://local")

import pytest
from langfuse.langchain import CallbackHandler

from jobadvaisor.llm import (
    ModelNotConfiguredError,
    chat_model,
    decider,
    embeddings,
    model_client,
    tracing,
)
from jobadvaisor.settings import Settings

ROUTER = "https://router.example.com/v1"


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_model_client_is_built_from_a_model_and_base_url_pair():
    config = settings(llm_model="openai/default-model", llm_base_url=ROUTER, llm_api_key="k")
    client = model_client("typesafe/other-model", "https://other.example.com/v1", config)
    assert (client.model_name, client.openai_api_base) == ("typesafe/other-model",
                                                          "https://other.example.com/v1")
    assert client.openai_api_key.get_secret_value() == "k"


def test_role_falls_back_to_llm_model_and_base_url():
    config = settings(llm_model="openai/default-model", llm_base_url=ROUTER,
                      llm_api_key="k", judge_model="openai/judge-model",
                      judge_base_url="https://judge.example.com")
    extractor, judge = chat_model("extractor", config), chat_model("judge", config)
    assert (extractor.model_name, extractor.openai_api_base) == ("openai/default-model", ROUTER)
    assert (judge.model_name, judge.openai_api_base) == ("openai/judge-model",
                                                         "https://judge.example.com")


def test_role_without_any_model_names_the_missing_settings():
    with pytest.raises(ModelNotConfiguredError, match="AGENT_MODEL or LLM_MODEL"):
        chat_model("agent", settings())


def test_llm_api_key_reaches_chat_embedding_and_decider_clients():
    config = settings(llm_model="openai/m", llm_base_url=ROUTER, llm_api_key="router-key",
                      embedding_model="openai/e", decider_model="typesafe/jev")
    assert chat_model("intake", config).openai_api_key.get_secret_value() == "router-key"
    assert embeddings(config).openai_api_key.get_secret_value() == "router-key"
    assert decider(config).client.api_key == "router-key"


def test_router_embeddings_send_text_not_token_ids():
    config = settings(llm_base_url=ROUTER, llm_api_key="k", embedding_model="openai/e")
    assert embeddings(config).check_embedding_ctx_length is False


def test_decider_reads_its_own_settings_with_llm_base_url_as_fallback():
    config = settings(llm_base_url=ROUTER, llm_api_key="k", decider_model="typesafe/jev")
    assert (decider(config).model, str(decider(config).client.base_url)) == ("typesafe/jev",
                                                                            ROUTER + "/")
    override = settings(llm_base_url=ROUTER, llm_api_key="k", decider_model="typesafe/jev",
                        decider_base_url="https://decider.example.com/v1")
    assert str(decider(override).client.base_url) == "https://decider.example.com/v1/"


def test_decider_is_none_without_decider_model():
    assert decider(settings(llm_api_key="k")) is None


def test_tracing_stays_off_without_both_langfuse_keys():
    assert tracing(settings()) == []
    assert tracing(settings(langfuse_public_key="pk-lf-x")) == []
    assert not chat_model("judge", settings(llm_model="openai/m", llm_base_url=ROUTER,
                                                llm_api_key="k")).callbacks


def test_tracing_attaches_a_langfuse_handler_to_chat_models_with_both_keys():
    config = settings(llm_model="openai/m", llm_base_url=ROUTER, llm_api_key="k",
                      langfuse_public_key="pk-lf-x",
                      langfuse_secret_key="sk-lf-x", langfuse_base_url="https://langfuse.example.com")
    [handler] = chat_model("judge", config).callbacks
    assert isinstance(handler, CallbackHandler)

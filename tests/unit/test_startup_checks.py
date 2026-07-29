import logging
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

import jarvis.startup_checks as startup_checks
from jarvis.llm.config import LLMSettings
from jarvis.llm.errors import (
    LLMConfigurationError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from jarvis.memory import knowledge
from jarvis.startup_checks import (
    ChatTarget,
    check_chat_providers,
    check_embedding_model,
    discover_active_chat_targets,
    run_model_startup_checks,
)


class FakeModel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeAdapter:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def create_model(self, provider, model_id, thinking, request_timeout=None):
        self.calls.append((provider, model_id, thinking, request_timeout))
        return self.model


class AuthenticationFailure(Exception):
    status_code = 401


class FakeEmbeddings:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def embed_query(self, text):
        self.calls.append(text)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _settings() -> LLMSettings:
    return LLMSettings.model_validate(
        {
            "providers": {
                "alpha": {
                    "adapter": "deepseek",
                    "api_key_env": "ALPHA_API_KEY",
                },
                "beta": {
                    "adapter": "openai_compatible",
                    "api_key_env": "BETA_API_KEY",
                },
                "unused": {
                    "adapter": "anthropic",
                    "api_key_env": "UNUSED_API_KEY",
                },
            },
            "profiles": {
                "answer": {
                    "model": "alpha/model-a",
                    "tools": "enabled",
                    "thinking": {"mode": "disabled"},
                },
                "reflection": {
                    "model": "alpha/model-b",
                    "tools": "disabled",
                    "thinking": {"mode": "disabled"},
                },
                "agent_dispatch": {
                    "model": "beta/model-c",
                    "tools": "disabled",
                    "thinking": {"mode": "disabled"},
                },
            },
        }
    )


def test_discovers_one_model_per_active_provider():
    assert discover_active_chat_targets(_settings()) == [
        ChatTarget(provider_name="alpha", model_id="model-a"),
        ChatTarget(provider_name="beta", model_id="model-c"),
    ]


def test_chat_check_invokes_each_active_provider_once(caplog):
    alpha_model = FakeModel(AIMessage(content="OK"))
    beta_model = FakeModel(AIMessage(content="OK"))
    adapters = {
        "deepseek": FakeAdapter(alpha_model),
        "openai_compatible": FakeAdapter(beta_model),
    }

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        check_chat_providers(_settings(), adapters=adapters)

    assert len(alpha_model.calls) == 1
    assert len(beta_model.calls) == 1
    assert isinstance(alpha_model.calls[0][0], HumanMessage)
    assert adapters["deepseek"].calls[0][3] == 10.0
    assert adapters["openai_compatible"].calls[0][3] == 10.0
    assert (
        "【供应商:alpha】【模型:model-a】【类型:Chat】【结果:成功】 "
        "Startup connectivity check completed"
    ) in caplog.text
    assert (
        "【供应商:beta】【模型:model-c】【类型:Chat】【结果:成功】 "
        "Startup connectivity check completed"
    ) in caplog.text
    assert caplog.text.count("Startup connectivity check completed") == 2


def test_chat_check_redacts_failure_and_continues(caplog):
    alpha_model = FakeModel(AuthenticationFailure("secret-response-body"))
    beta_model = FakeModel(AIMessage(content="OK"))
    adapters = {
        "deepseek": FakeAdapter(alpha_model),
        "openai_compatible": FakeAdapter(beta_model),
    }

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        check_chat_providers(_settings(), adapters=adapters)

    assert (
        "【供应商:alpha】【模型:model-a】【类型:Chat】【结果:失败】"
        "【类别:credential】 Startup connectivity check failed"
    ) in caplog.text
    assert "secret-response-body" not in caplog.text
    assert len(beta_model.calls) == 1
    assert (
        "【供应商:beta】【模型:model-c】【类型:Chat】【结果:成功】 "
        "Startup connectivity check completed"
    ) in caplog.text


def test_embedding_check_invokes_active_model(caplog):
    embeddings = FakeEmbeddings([0.1, 0.2])

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        check_embedding_model(
            "siliconflow/Qwen/Qwen3-Embedding-8B",
            embeddings_factory=lambda: embeddings,
        )

    assert embeddings.calls == ["Jarvis startup connectivity check"]
    assert (
        "【供应商:siliconflow】【模型:Qwen/Qwen3-Embedding-8B】"
        "【类型:Embedding】【结果:成功】 Startup connectivity check completed"
    ) in caplog.text


def test_embedding_check_redacts_failure(caplog):
    embeddings = FakeEmbeddings(AuthenticationFailure("secret-response-body"))

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        check_embedding_model(
            "siliconflow/Qwen/Qwen3-Embedding-8B",
            embeddings_factory=lambda: embeddings,
        )

    assert (
        "【供应商:siliconflow】【模型:Qwen/Qwen3-Embedding-8B】"
        "【类型:Embedding】【结果:失败】【类别:credential】 "
        "Startup connectivity check failed"
    ) in caplog.text
    assert "secret-response-body" not in caplog.text


def test_embedding_check_uses_bounded_request_timeout(monkeypatch):
    embeddings = FakeEmbeddings([0.1])
    embeddings_factory = MagicMock(return_value=embeddings)
    monkeypatch.setattr(startup_checks, "_get_embeddings", embeddings_factory)

    check_embedding_model("siliconflow/embedding-model")

    embeddings_factory.assert_called_once_with(
        model_spec="siliconflow/embedding-model",
        request_timeout=10.0,
        max_retries=0,
    )


def test_embedding_check_rejects_unknown_provider_without_request(caplog):
    embeddings_factory = MagicMock()

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        check_embedding_model(
            "unknown/embedding-model",
            embeddings_factory=embeddings_factory,
        )

    embeddings_factory.assert_not_called()
    assert (
        "【供应商:unknown】【模型:unknown】【类型:Embedding】【结果:失败】"
        "【类别:configuration】 Startup connectivity check failed"
    ) in caplog.text


def test_embedding_check_reports_missing_key_as_credential(
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(knowledge, "SILICONFLOW_API_KEY", "")
    monkeypatch.setattr(startup_checks, "_get_embeddings", knowledge._get_embeddings)

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        check_embedding_model("siliconflow/embedding-model")

    assert (
        "【供应商:siliconflow】【模型:embedding-model】【类型:Embedding】"
        "【结果:失败】【类别:credential】 Startup connectivity check failed"
    ) in caplog.text


def test_failure_categories_distinguish_timeout_connectivity_and_credential():
    assert startup_checks.failure_category(LLMTimeoutError()) == "timeout"
    assert startup_checks.failure_category(LLMUnavailableError()) == "connectivity"
    assert startup_checks.failure_category(AuthenticationFailure()) == "credential"


def test_startup_checks_continue_to_embedding_when_chat_config_fails(caplog):
    embeddings = FakeEmbeddings([0.1])

    def fail_to_load_settings():
        raise RuntimeError("secret-config-detail")

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        run_model_startup_checks(
            settings_loader=fail_to_load_settings,
            embeddings_factory=lambda: embeddings,
            embedding_model_spec="siliconflow/embedding-model",
        )

    assert embeddings.calls == ["Jarvis startup connectivity check"]
    assert (
        "【供应商:unknown】【模型:unknown】【类型:Chat】【结果:失败】"
        "【类别:provider】 "
        "Could not load active provider configuration"
    ) in caplog.text
    assert "secret-config-detail" not in caplog.text
    assert "【类型:Embedding】【结果:成功】" in caplog.text


def test_invalid_chat_config_is_reported_as_configuration(caplog):
    embeddings = FakeEmbeddings([0.1])

    def fail_to_load_settings():
        raise LLMConfigurationError("secret-config-detail")

    with caplog.at_level(logging.INFO, logger="jarvis.startup_checks"):
        run_model_startup_checks(
            settings_loader=fail_to_load_settings,
            embeddings_factory=lambda: embeddings,
            embedding_model_spec="siliconflow/embedding-model",
        )

    assert (
        "【供应商:unknown】【模型:unknown】【类型:Chat】【结果:失败】"
        "【类别:configuration】 "
        "Could not load active provider configuration"
    ) in caplog.text
    assert "secret-config-detail" not in caplog.text

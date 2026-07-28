from unittest.mock import MagicMock, patch

import pytest

from jarvis.llm.errors import LLMConfigurationError
from jarvis.memory import knowledge


def test_siliconflow_embedding_configuration_is_unchanged(monkeypatch):
    monkeypatch.setattr(
        knowledge,
        "EMBED_MODEL",
        "siliconflow/Qwen/Qwen3-Embedding-8B",
    )
    monkeypatch.setattr(knowledge, "SILICONFLOW_API_KEY", "sf-key")
    monkeypatch.setattr(
        knowledge,
        "SILICONFLOW_BASE_URL",
        "https://api.siliconflow.cn/v1",
    )

    with patch.object(
        knowledge,
        "OpenAIEmbeddings",
        return_value=MagicMock(),
    ) as embeddings:
        knowledge._get_embeddings(request_timeout=10.0, max_retries=0)

    assert embeddings.call_args.kwargs == {
        "model": "Qwen/Qwen3-Embedding-8B",
        "api_key": "sf-key",
        "base_url": "https://api.siliconflow.cn/v1",
        "request_timeout": 10.0,
        "max_retries": 0,
    }


@pytest.mark.parametrize(
    "model_spec",
    [
        "model-without-provider",
        "unknown/model",
        "/model",
        "siliconflow/",
    ],
)
def test_invalid_embedding_provider_is_rejected(model_spec):
    with pytest.raises(
        LLMConfigurationError,
        match="embedding model configuration is invalid",
    ):
        knowledge._parse_embed_model(model_spec)


def test_explicit_empty_embedding_model_does_not_fall_back(monkeypatch):
    monkeypatch.setattr(
        knowledge,
        "EMBED_MODEL",
        "siliconflow/default-model",
    )

    with pytest.raises(
        LLMConfigurationError,
        match="embedding model configuration is invalid",
    ):
        knowledge._get_embeddings(model_spec="")

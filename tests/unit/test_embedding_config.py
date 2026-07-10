from unittest.mock import MagicMock, patch

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
        knowledge._get_embeddings()

    assert embeddings.call_args.kwargs == {
        "model": "Qwen/Qwen3-Embedding-8B",
        "api_key": "sf-key",
        "base_url": "https://api.siliconflow.cn/v1",
    }

import pytest
from types import SimpleNamespace
from qdrant_client import QdrantClient
from unittest.mock import patch, MagicMock


def test_store_and_retrieve_knowledge():
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 4096

    mock_client = MagicMock(spec=QdrantClient)
    mock_client.get_collections.return_value.collections = []
    mock_result = MagicMock()
    mock_result.score = 0.9
    mock_result.payload = {"text": "Paris is the capital of France."}
    mock_client.query_points.return_value.points = [mock_result]

    with patch("jarvis.memory.knowledge._get_embeddings", return_value=mock_embeddings), \
         patch("jarvis.memory.knowledge._get_client", return_value=mock_client):
        from jarvis.memory.knowledge import init_collection, store_knowledge, retrieve_knowledge
        init_collection()
        store_knowledge("Paris is the capital of France.", "https://example.com", "user1")
        result = retrieve_knowledge("What is the capital of France?", "user1")

    assert "Paris" in result
    mock_client.upsert.assert_called_once()
    mock_client.query_points.assert_called_once()


def test_retrieval_filters_irrelevant_and_quarantined_points_and_caps_context(monkeypatch):
    from jarvis.memory import knowledge

    monkeypatch.setattr(knowledge, "RAG_MAX_DOCUMENT_CHARS", 10, raising=False)
    monkeypatch.setattr(knowledge, "RAG_MAX_CONTEXT_CHARS", 25, raising=False)
    monkeypatch.setattr(knowledge, "RAG_MIN_SCORE", 0.70, raising=False)
    client = MagicMock(spec=QdrantClient)
    client.query_points.return_value.points = [
        SimpleNamespace(score=0.99, payload={"text": "quarantined", "rag_quarantined": True}),
        SimpleNamespace(score=0.95, payload={"text": "a" * 50}),
        SimpleNamespace(score=0.9, payload={"text": "b" * 50}),
        SimpleNamespace(score=0.63, payload={"text": "unrelated"}),
    ]
    with patch.object(knowledge, "_get_client", return_value=client), patch.object(
        knowledge, "_get_embeddings"
    ):
        assert knowledge.retrieve_knowledge("real question", "u1") == "aaaaaaaaaa\n\n---\n\nbbbbbbbb"

    kwargs = client.query_points.call_args.kwargs
    assert kwargs["score_threshold"] == 0.70
    assert kwargs["query_filter"].must[0].match.value == "u1"
    assert kwargs["query_filter"].must_not[0].key == "rag_quarantined"


def test_retrieval_returns_empty_when_no_point_meets_threshold(monkeypatch):
    from jarvis.memory import knowledge

    monkeypatch.setattr(knowledge, "RAG_MIN_SCORE", 0.70, raising=False)
    client = MagicMock(spec=QdrantClient)
    client.query_points.return_value.points = [
        SimpleNamespace(score=0.6373, payload={"text": "unrelated"}),
    ]
    with patch.object(knowledge, "_get_client", return_value=client), patch.object(
        knowledge, "_get_embeddings"
    ):
        assert knowledge.retrieve_knowledge("question", "u1") == ""

import pytest
from unittest.mock import patch, MagicMock


def test_store_and_retrieve_knowledge():
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 4096

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = []
    mock_result = MagicMock()
    mock_result.payload = {"text": "Paris is the capital of France."}
    mock_client.search.return_value = [mock_result]

    with patch("jarvis.memory.knowledge._get_embeddings", return_value=mock_embeddings), \
         patch("jarvis.memory.knowledge._get_client", return_value=mock_client):
        from jarvis.memory.knowledge import init_collection, store_knowledge, retrieve_knowledge
        init_collection()
        store_knowledge("Paris is the capital of France.", "https://example.com", "user1")
        result = retrieve_knowledge("What is the capital of France?", "user1")

    assert "Paris" in result
    mock_client.upsert.assert_called_once()
    mock_client.search.assert_called_once()

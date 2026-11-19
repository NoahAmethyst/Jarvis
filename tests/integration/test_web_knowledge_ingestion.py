import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from unittest.mock import MagicMock, patch

from jarvis.agent.nodes.memory_write import memory_write
from jarvis.memory import knowledge


REPORT = "City engineers measured 42 millimeters of rainfall during the May 2026 monitoring period."
REPORT_2 = "The official weather archive recorded 31 millimeters of rainfall at the coastal station in May 2026."
OFF_TOPIC = "The advertising agency has just released a promotional guide about luxury watches."
POOR = "Subscribe for unlimited access. This sponsored post contains affiliate links. Sign in to continue reading."


@pytest.fixture
def local_knowledge(monkeypatch):
    client = QdrantClient(":memory:")
    embeddings = MagicMock()
    embeddings.embed_query.return_value = [0.1, 0.2]
    monkeypatch.setattr(knowledge, "_get_client", lambda: client)
    monkeypatch.setattr(knowledge, "_get_embeddings", lambda: embeddings)
    monkeypatch.setattr(knowledge, "VECTOR_SIZE", 2)
    knowledge.init_collection()
    yield client, embeddings
    client.close()


def source(url, text):
    return {"url": url, "text": text, "title": "Report"}


def state(sources, name="web_search", user="u1", status="success"):
    return {"user_id": user, "query": "May rainfall", "messages": [
        HumanMessage(content="May rainfall"),
        ToolMessage(content="Tool output is not the source of truth", name=name,
                    tool_call_id="c1", artifact={"sources": sources}, status=status),
        AIMessage(content="Final response"),
    ]}


def reviewed(decisions):
    return AIMessage(content=json.dumps(decisions))


def rows(client):
    return [point.payload for point in client.scroll(knowledge.COLLECTION_NAME)[0]]


def test_web_results_reviewed_per_source_before_embedding(local_knowledge, caplog):
    client, embeddings = local_knowledge
    results = [
        source("https://CITY.example/report?utm_source=tavily#headline", REPORT + "\n" + POOR),
        source("https://weather.example/report", REPORT_2),
        source("https://irrelevant.example", OFF_TOPIC),
        source("https://poor.example", POOR),
        source("https://mirror.example/report", REPORT_2 + "  "),
        source("file:///private", REPORT),
    ]
    with patch("jarvis.llm.llm.chat", return_value=reviewed([
        {"id": 0, "decision": "accept", "excerpt": REPORT},
        {"id": 1, "decision": "accept", "excerpt": REPORT_2},
        {"id": 2, "decision": "irrelevant"},
        {"id": 3, "decision": "low_quality"},
    ])) as review, patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"), caplog.at_level(logging.INFO):
        memory_write(state(results))

    review.assert_called_once()
    assert review.call_args.kwargs["profile"] == "reflection"
    assert review.call_args.kwargs["tools"] is None
    sent = json.loads(review.call_args.kwargs["messages"][1].content)
    assert sent["query"] == "May rainfall"
    assert [item["id"] for item in sent["sources"]] == [0, 1, 2, 3]
    assert {row["source_url"]: row["text"] for row in rows(client)} == {
        "https://city.example/report": REPORT, "https://weather.example/report": REPORT_2,
    }
    assert [call.args[0] for call in embeddings.embed_query.call_args_list] == [REPORT, REPORT_2]
    assert "【动作:知识审核】" in caplog.text and "【知识落库数:2】" in caplog.text
    assert REPORT not in caplog.text and "https://city.example" not in caplog.text


@pytest.mark.parametrize("output", [
    AIMessage(content="not JSON"),
    reviewed([{"id": 0, "decision": "accept", "excerpt": "An invented but sufficiently long claim."}]),
    reviewed([{"id": 0, "decision": "accept", "excerpt": REPORT}, {"id": 0, "decision": "low_quality"}]),
    reviewed([{"id": False, "decision": "accept", "excerpt": REPORT}]),
    RuntimeError("private-provider-error"),
])
def test_review_uncertainty_never_writes_unreviewed_data(local_knowledge, output):
    client, embeddings = local_knowledge
    response = {"side_effect": output} if isinstance(output, Exception) else {"return_value": output}
    with patch("jarvis.llm.llm.chat", **response), patch(
        "jarvis.agent.nodes.memory_write.conv_mem.save_message"
    ) as conversation:
        assert memory_write(state([source("https://city.example/report", REPORT)])) == {}

    assert conversation.call_count == 2
    assert rows(client) == []
    embeddings.embed_query.assert_not_called()


def test_repeat_writes_keep_modern_and_legacy_quarantine_and_user_scope(local_knowledge):
    client, embeddings = local_knowledge
    url = "https://city.example/report"
    legacy_url = "https://old.example/may"
    old_content = f"Title: Archived data\nURL: {legacy_url}?utm_source=old\n{REPORT_2}"
    client.upsert(knowledge.COLLECTION_NAME, [PointStruct(id=42, vector=[0.1, 0.2], payload={
        "user_id": "u1", "source_url": "tool:web_search", "text": old_content, "rag_quarantined": True,
    })])
    with patch("jarvis.llm.llm.chat", return_value=reviewed([
        {"id": 0, "decision": "accept", "excerpt": REPORT},
    ])) as review, patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"):
        memory_write(state([source(url, REPORT)]))
        points, _ = client.scroll(knowledge.COLLECTION_NAME)
        client.set_payload(knowledge.COLLECTION_NAME, {"rag_quarantined": True}, points=[p.id for p in points])
        review.reset_mock()
        embeddings.reset_mock()

        memory_write(state([
            source(url + "?utm_medium=new", REPORT_2),
            source(legacy_url + "#date", REPORT),
        ], name="web_scrape"))
        memory_write(state([source("https://mirror.example/may", REPORT_2)]))
        review.assert_not_called()
        embeddings.embed_query.assert_not_called()
        assert len(rows(client)) == 2 and all(row["rag_quarantined"] for row in rows(client))

        # Explicit ingestion doesn't review new data but cannot reactivate quarantined web data.
        assert not knowledge.store_knowledge(REPORT_2, "https://different.example/may", "u1")
        assert not knowledge.store_knowledge(OFF_TOPIC, url + "?utm_source=another", "u1")
        embeddings.embed_query.assert_not_called()

        memory_write(state([source(url, REPORT)], user="u2"))
        assert review.call_count == 1
        assert any(row["user_id"] == "u2" and not row.get("rag_quarantined") for row in rows(client))


@pytest.mark.parametrize("extraction", [REPORT, REPORT_2 + " " + REPORT + " Archived appendix."])
def test_copied_parts_of_legacy_quarantine_do_not_return_through_mirrors(local_knowledge, extraction):
    client, embeddings = local_knowledge
    original = REPORT_2 + " " + REPORT
    client.upsert(knowledge.COLLECTION_NAME, [PointStruct(id=42, vector=[0.1, 0.2], payload={
        "user_id": "u1", "source_url": "tool:web_search", "rag_quarantined": True,
        "text": f"Title: Archived\nURL: https://old.example/report\n{original}",
    })])
    mirror = "May monitoring. " + extraction + " Additional site content."
    with patch("jarvis.llm.llm.chat", return_value=reviewed([
        {"id": 0, "decision": "accept", "excerpt": extraction},
    ])) as review, patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"):
        memory_write(state([source("https://mirror.example/may", mirror)]))

    review.assert_called_once()
    embeddings.embed_query.assert_not_called()
    assert len(rows(client)) == 1 and rows(client)[0]["rag_quarantined"] is True


def test_duplicate_evidence_across_requests_is_not_embedded_twice(local_knowledge):
    client, embeddings = local_knowledge
    with patch("jarvis.llm.llm.chat", return_value=reviewed([
        {"id": 0, "decision": "accept", "excerpt": REPORT},
    ])), patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"):
        memory_write(state([source("https://city.example/report", REPORT)]))
        # Different URL and raw page but the reviewed excerpt is already stored.
        memory_write(state([source("https://mirror.example/report", REPORT + "\n" + POOR)]))

    embeddings.embed_query.assert_called_once_with(REPORT)
    assert len(rows(client)) == 1


def test_concurrent_mirrors_in_same_worker_store_one_excerpt(local_knowledge):
    client, embeddings = local_knowledge
    barrier = Barrier(2, timeout=5)

    def review(**kwargs):
        barrier.wait()
        return reviewed([{"id": 0, "decision": "accept", "excerpt": REPORT}])

    def write(url):
        return memory_write(state([source(url, REPORT)]))

    with patch("jarvis.llm.llm.chat", side_effect=review), patch(
        "jarvis.agent.nodes.memory_write.conv_mem.save_message"
    ), ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(write, ["https://city.example/report", "https://mirror.example/report"])) == [{}, {}]

    embeddings.embed_query.assert_called_once_with(REPORT)
    assert len(rows(client)) == 1


@pytest.mark.parametrize("name,status", [("other_tool", "success"), ("web_search", "error")])
def test_only_successful_web_tools_create_candidates(local_knowledge, name, status):
    client, embeddings = local_knowledge
    with patch("jarvis.llm.llm.chat") as review, patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"):
        memory_write(state([source("https://city.example/report", REPORT)], name=name, status=status))

    review.assert_not_called()
    embeddings.embed_query.assert_not_called()
    assert rows(client) == []

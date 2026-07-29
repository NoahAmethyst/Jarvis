import logging
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from jarvis.agent.nodes.memory_write import memory_write


def test_memory_write_keeps_tool_transcript_out_of_conversation_storage():
    tool_call = AIMessage(
        content="",
        tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "call-1"}],
        additional_kwargs={"reasoning_content": "private reasoning"},
    )
    tool_result = "knowledge result " * 30
    state = {
        "messages": [
            HumanMessage(content="question"),
            tool_call,
            ToolMessage(
                content=tool_result,
                tool_call_id="call-1",
                name="web_search",
            ),
            AIMessage(content="final answer"),
        ],
        "user_id": "u1",
    }

    with patch(
        "jarvis.agent.nodes.memory_write.conv_mem.save_message"
    ) as save_message, patch(
        "jarvis.agent.nodes.memory_write.know_mem.store_knowledge"
    ) as store_knowledge:
        memory_write(state)

    assert save_message.call_args_list == [
        (("u1", "human", "question"),),
        (("u1", "ai", "final answer"),),
    ]
    store_knowledge.assert_called_once_with(
        tool_result,
        "tool:web_search",
        "u1",
    )


def test_short_tool_result_is_not_persisted_as_knowledge():
    state = {
        "messages": [
            HumanMessage(content="question"),
            ToolMessage(content="short", tool_call_id="call-1", name="web_search"),
            AIMessage(content="final answer"),
        ],
        "user_id": "u1",
    }

    with patch(
        "jarvis.agent.nodes.memory_write.conv_mem.save_message"
    ), patch(
        "jarvis.agent.nodes.memory_write.know_mem.store_knowledge"
    ) as store_knowledge:
        memory_write(state)

    store_knowledge.assert_not_called()


def test_memory_write_failure_log_is_labeled_and_redacted(caplog):
    state = {
        "messages": [HumanMessage(content="question")],
        "user_id": "u1",
    }

    with caplog.at_level(logging.WARNING, logger="jarvis.agent.nodes.memory_write"):
        with patch(
            "jarvis.agent.nodes.memory_write.conv_mem.save_message",
            side_effect=RuntimeError("secret-database-detail"),
        ):
            memory_write(state)

    assert (
        "【节点:memory_write】【组件:PostgreSQL】【状态:降级】"
        "【错误:RuntimeError】 Could not save conversation history"
    ) in caplog.text
    assert "secret-database-detail" not in caplog.text


def test_memory_load_fallback_log_is_labeled_and_redacted(caplog):
    from jarvis.agent.nodes.memory_load import memory_load

    with caplog.at_level(logging.WARNING, logger="jarvis.agent.nodes.memory_load"):
        with patch(
            "jarvis.agent.nodes.memory_load.conv_mem.load_history",
            side_effect=RuntimeError("secret-database-detail"),
        ):
            result = memory_load({"user_id": "u1"})

    assert result == {"history": []}
    assert (
        "【节点:memory_load】【组件:PostgreSQL】【状态:降级】"
        "【错误:RuntimeError】 History unavailable"
    ) in caplog.text
    assert "secret-database-detail" not in caplog.text


def test_rag_retrieve_fallback_log_is_labeled_and_redacted(caplog):
    from jarvis.agent.nodes.rag_retrieve import rag_retrieve

    state = {"query": "question", "user_id": "u1"}
    with caplog.at_level(logging.WARNING, logger="jarvis.agent.nodes.rag_retrieve"):
        with patch(
            "jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge",
            side_effect=RuntimeError("secret-qdrant-detail"),
        ):
            result = rag_retrieve(state)

    assert result == {"rag_context": ""}
    assert (
        "【节点:rag_retrieve】【组件:Qdrant】【状态:降级】"
        "【错误:RuntimeError】 Retrieval unavailable"
    ) in caplog.text
    assert "secret-qdrant-detail" not in caplog.text


def test_postgresql_initialization_log_is_labeled(caplog):
    from jarvis.memory import conversation

    connection = MagicMock()
    with caplog.at_level(logging.INFO, logger="jarvis.memory.conversation"):
        with patch(
            "jarvis.memory.conversation._get_conn",
            return_value=connection,
        ):
            conversation.init_db()

    assert (
        "【组件:PostgreSQL】【状态:就绪】 Conversation storage initialized"
    ) in caplog.text


def test_qdrant_initialization_log_is_labeled(caplog):
    from jarvis.memory import knowledge

    client = MagicMock()
    client.get_collections.return_value.collections = []
    with caplog.at_level(logging.INFO, logger="jarvis.memory.knowledge"):
        with patch(
            "jarvis.memory.knowledge._get_client",
            return_value=client,
        ):
            knowledge.init_collection()

    assert (
        "【组件:Qdrant】【集合:jarvis_knowledge】【状态:就绪】 "
        "Knowledge collection initialized"
    ) in caplog.text

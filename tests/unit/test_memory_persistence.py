import logging
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from jarvis.agent.nodes.memory_write import memory_write
from jarvis.memory import conversation


def test_only_selected_final_answer_is_written_in_one_statement(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(conversation, "_get_conn", lambda: connection)
    memory_write({
        "user_id": "fixture", "query": "current question", "final_answer": "selected answer",
        "messages": [HumanMessage(content="current question"), AIMessage(content="draft one"),
                     AIMessage(content="selected answer"), AIMessage(content="not selected")],
    })
    assert cursor.execute.call_count == 2
    lock_statement, lock_params = cursor.execute.call_args_list[0].args
    assert "pg_advisory_xact_lock" in lock_statement and isinstance(lock_params[0], int)
    statement, params = cursor.execute.call_args.args
    assert "INSERT INTO conversations" in statement
    assert statement.count("statement_timestamp()") == 2
    assert params == ("fixture", "current question", "fixture", "selected answer")
    connection.commit.assert_called_once()


def test_absent_final_answer_does_not_write_a_partial_turn(monkeypatch):
    connection = MagicMock()
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(conversation, "_get_conn", connect)
    memory_write({
        "user_id": "fixture", "query": "incomplete question", "final_answer": "",
        "messages": [HumanMessage(content="incomplete question"), AIMessage(content="draft only")],
    })
    connect.assert_not_called()


@pytest.mark.parametrize("records,expected", [
    ([('ai', 'orphan draft'), ('ai', 'orphan final'), ('human', 'question one'),
      ('ai', 'draft one'), ('ai', 'draft two'), ('ai', 'final one'), ('human', 'question two'),
      ('ai', 'final two'), ('human', 'unanswered')],
     [('human', 'question one'), ('ai', 'final one'), ('human', 'question two'), ('ai', 'final two')]),
    ([('human', 'no reply'), ('human', 'other question'), ('ai', 'draft no good'), ('ai', '  '),
      ('human', 'valid question'), ('ai', 'valid answer')],
     [('human', 'valid question'), ('ai', 'valid answer')]),
    ([('ai', 'only orphan')], []),
])
def test_history_selects_only_final_replies_from_complete_turns(monkeypatch, records, expected):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [dict(role=role, content=content, created_at=i)
                                    for i, (role, content) in reversed(list(enumerate(records)))]
    monkeypatch.setattr(conversation, "_get_conn", lambda: connection)
    result = conversation.load_history("fixture", limit=len(records))
    assert [(message.type, message.content) for message in result] == expected
    statement, params = cursor.execute.call_args.args
    assert "ORDER BY created_at DESC, id DESC" in statement
    assert params == ("fixture", len(records))
    connection.commit.assert_not_called()


def test_new_atomic_pair_is_not_overridden_by_a_late_legacy_reply(monkeypatch):
    records = [('human', 'legacy question', 1), ('human', 'new question', 2),
               ('ai', 'paired new answer', 2), ('ai', 'late legacy reply', 3)]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchall.return_value = [
        dict(role=role, content=content, created_at=timestamp)
        for role, content, timestamp in reversed(records)
    ]
    monkeypatch.setattr(conversation, "_get_conn", lambda: connection)
    result = conversation.load_history("fixture")
    assert [(message.type, message.content) for message in result] == [
        ('human', 'new question'), ('ai', 'paired new answer'),
    ]


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
        "query": "question",
        "final_answer": "final answer",
    }

    with patch(
        "jarvis.agent.nodes.memory_write.conv_mem.save_turn"
    ) as save_turn, patch(
        "jarvis.memory.knowledge.store_web_knowledge"
    ) as store_knowledge:
        memory_write(state)

    save_turn.assert_called_once_with("u1", "question", "final answer")
    store_knowledge.assert_not_called()


def test_short_tool_result_is_not_persisted_as_knowledge():
    state = {
        "messages": [
            HumanMessage(content="question"),
            ToolMessage(content="short", tool_call_id="call-1", name="web_search"),
            AIMessage(content="final answer"),
        ],
        "user_id": "u1",
        "query": "question",
        "final_answer": "final answer",
    }

    with patch(
        "jarvis.agent.nodes.memory_write.conv_mem.save_turn"
    ), patch(
        "jarvis.memory.knowledge.store_web_knowledge"
    ) as store_knowledge:
        memory_write(state)

    store_knowledge.assert_not_called()


def test_memory_write_failure_log_is_labeled_and_redacted(caplog):
    state = {
        "messages": [HumanMessage(content="question"), AIMessage(content="answer")],
        "user_id": "u1",
        "query": "question",
        "final_answer": "answer",
    }

    with caplog.at_level(logging.WARNING, logger="jarvis.agent.nodes.memory_write"):
        with patch(
            "jarvis.agent.nodes.memory_write.conv_mem.save_turn",
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

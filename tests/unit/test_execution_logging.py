import logging
import re
import pytest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from jarvis.execution_logging import request_trace
from jarvis.logging_config import format_log_tags


def _state():
    return {
        "messages": [HumanMessage(content="private-question")],
        "history": [], "user_id": "private-user", "query": "private-question",
        "rag_context": "", "reflection_score": 0.0, "retry_count": 0,
        "final_answer": "", "low_confidence": False, "llm_override": None,
        "reflect_llm_override": None, "active_agent": None,
        "agent_dispatch_score": 0.0, "unavailable_tools": [],
    }


def test_request_context_isolated_and_failure_redacted(caplog):
    with caplog.at_level(logging.INFO):
        with request_trace("test"):
            first = format_log_tags(("动作", "test"))
        try:
            with request_trace("test"):
                second = format_log_tags(("动作", "test"))
                raise RuntimeError("private-secret")
        except RuntimeError:
            pass
    assert first != second
    assert "【请求ID:" in first
    assert "【请求ID:" not in format_log_tags(("动作", "outside"))
    assert "【状态:失败】" in caplog.text
    assert "private-secret" not in caplog.text


def test_concurrent_requests_do_not_mix_ids():
    def run(_):
        with request_trace("test"):
            return format_log_tags(("动作", "test"))
    with ThreadPoolExecutor(max_workers=4) as executor:
        values = list(executor.map(run, range(8)))
    assert len(set(values)) == 8


def test_graph_logs_actions_and_results_with_same_request_id(caplog):
    from jarvis.agent.graph import graph
    state = _state()
    with caplog.at_level(logging.INFO), patch(
        "jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[]
    ), patch("jarvis.agent.nodes.agent_dispatch.load_agents", return_value=[]), patch(
        "jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value="private-knowledge"
    ), patch("jarvis.agent.nodes.plan_and_call.llm.chat", side_effect=[
        AIMessage(content="private-answer"), AIMessage(content="0.95")
    ]), patch("jarvis.agent.nodes.memory_write.conv_mem.save_message"):
        with request_trace("test"):
            graph.invoke(state)
    for node in ("memory_load", "agent_dispatch", "rag_retrieve", "plan_and_call", "reflect", "memory_write"):
        assert f"【节点:{node}】" in caplog.text
    assert "【评分:0.95】" in caplog.text
    assert "【历史条数:0】" in caplog.text
    assert "【状态:跳过】" in caplog.text
    ids = re.findall(r"【请求ID:([^】]+)】", caplog.text)
    assert len(ids) > 10 and len(set(ids)) == 1
    for text in ("private-question", "private-user", "private-knowledge", "private-answer"):
        assert text not in caplog.text


def test_knowledge_length_check_and_storage_feedback(caplog):
    from jarvis.agent.nodes.memory_write import memory_write
    state = {"user_id": "u", "messages": [
        ToolMessage(content="short", tool_call_id="1", name="web_search"),
        ToolMessage(content="x" * 300, tool_call_id="2", name="web_scrape"),
    ]}
    with caplog.at_level(logging.INFO), request_trace("test"), patch(
        "jarvis.agent.nodes.memory_write.know_mem.store_knowledge"
    ) as store:
        memory_write(state)
    assert store.call_count == 1
    assert "【动作:知识长度校验】" in caplog.text
    assert "【结果:跳过】" in caplog.text
    assert "【结果:通过】" in caplog.text
    assert "【知识落库数:1】" in caplog.text


def test_tool_result_and_unavailable_outcomes(caplog):
    from jarvis.agent.nodes.tool_execute import execute_tools
    from jarvis.tools.errors import ToolUnavailableError
    registration = SimpleNamespace(missing_env_vars=lambda: [], tool=MagicMock())
    registration.tool.invoke.side_effect = ["private-tool-result", ToolUnavailableError("web_search", "timeout")]
    state = {"messages": [AIMessage(content="", tool_calls=[
        {"name": "web_search", "args": {"query": "private-query"}, "id": "1"},
        {"name": "web_search", "args": {"query": "private-query"}, "id": "2"},
    ])], "unavailable_tools": []}
    with caplog.at_level(logging.INFO), request_trace("test"), patch(
        "jarvis.agent.nodes.tool_execute.get_tool_registration", return_value=registration
    ):
        result = execute_tools(state)
    assert result["unavailable_tools"] == ["web_search"]
    assert "【动作:执行工具】" in caplog.text
    assert "【结果字符数:19】" in caplog.text
    assert "【状态:降级】" in caplog.text and "【类别:timeout】" in caplog.text
    assert "private-tool-result" not in caplog.text and "private-query" not in caplog.text


def test_knowledge_query_and_upsert_log_real_counts(caplog):
    from jarvis.memory.knowledge import retrieve_knowledge, store_knowledge
    embeddings = MagicMock()
    embeddings.embed_query.return_value = [0.1, 0.2]
    client = MagicMock()
    client.query_points.return_value.points = [SimpleNamespace(payload={"text": "private-knowledge"})]
    with caplog.at_level(logging.INFO), request_trace("test"), patch(
        "jarvis.memory.knowledge._get_embeddings", return_value=embeddings
    ), patch("jarvis.memory.knowledge._get_client", return_value=client):
        assert retrieve_knowledge("private-query", "private-user") == "private-knowledge"
        store_knowledge("private-knowledge", "private-source", "private-user")
    for tag in ("【动作:查询知识库】", "【命中数:1】", "【动作:知识落库】", "【写入数:1】", "【向量维度:2】"):
        assert tag in caplog.text
    for value in ("private-query", "private-user", "private-source", "private-knowledge"):
        assert value not in caplog.text


def test_partial_persistence_and_degraded_node_are_not_reported_as_success(caplog):
    from jarvis.agent.nodes.memory_write import memory_write
    state = {"user_id": "u", "messages": [HumanMessage(content="hi"), AIMessage(content="hello")]}
    with caplog.at_level(logging.INFO), request_trace("test"), patch(
        "jarvis.agent.nodes.memory_write.conv_mem.save_message", side_effect=[None, RuntimeError("private-error")]
    ):
        memory_write(state)
    last = next(record.getMessage() for record in reversed(caplog.records)
                if "【节点:memory_write】" in record.getMessage())
    assert "【状态:降级】" in last and "【历史落库数:1】" in last
    assert "【降级节点数:1】" in caplog.records[-1].getMessage()
    assert "private-error" not in caplog.text


@pytest.mark.parametrize("branch", ["tools", "reflection_retry"])
def test_graph_traces_tool_loop_and_reflection_retry(branch, caplog):
    from jarvis.agent.graph import graph
    tool_response = AIMessage(content="", tool_calls=[
        {"name": "web_search", "args": {"query": "private-search"}, "id": "call-1"},
    ])
    responses = ([tool_response, AIMessage(content="private-answer"), AIMessage(content="0.95")]
                 if branch == "tools" else [AIMessage(content="draft"), AIMessage(content="0.2"),
                                            AIMessage(content="final"), AIMessage(content="0.95")])
    registration = SimpleNamespace(missing_env_vars=lambda: [], tool=MagicMock())
    registration.tool.invoke.return_value = "x" * 300
    with caplog.at_level(logging.INFO), patch(
        "jarvis.agent.nodes.memory_load.conv_mem.load_history", return_value=[]
    ), patch("jarvis.agent.nodes.agent_dispatch.load_agents", return_value=[]), patch(
        "jarvis.agent.nodes.rag_retrieve.know_mem.retrieve_knowledge", return_value=""
    ), patch("jarvis.agent.nodes.plan_and_call.llm.chat", side_effect=responses), patch(
        "jarvis.agent.nodes.memory_write.conv_mem.save_message"
    ), patch("jarvis.agent.nodes.memory_write.know_mem.store_knowledge") as store, patch(
        "jarvis.agent.nodes.tool_execute.get_tool_registration", return_value=registration
    ):
        with request_trace("test"):
            graph.invoke(_state())
    if branch == "tools":
        assert store.call_count == 1 and "【知识落库数:1】" in caplog.text
        assert "【工具:web_search】" in caplog.text
    else:
        assert "【评分:0.20】" in caplog.text and "【状态:重试】" in caplog.text
        assert "【轮次:2】" in caplog.text
    assert "【节点执行次数:8】" in caplog.text
    assert len(set(re.findall(r"【请求ID:([^】]+)】", caplog.text))) == 1
    assert "private-search" not in caplog.text and "private-answer" not in caplog.text


def test_grpc_failure_has_failed_request_summary(caplog):
    from jarvis.api.grpc.servicer import JarvisServicer
    from jarvis.api.grpc.jarvis_pb2 import ChatRequest
    from tests.unit.test_grpc_servicer import FakeContext
    context = FakeContext()
    with caplog.at_level(logging.INFO), patch(
        "jarvis.api.grpc.servicer.graph.invoke", side_effect=RuntimeError("private-error")
    ):
        JarvisServicer().Chat(ChatRequest(message="private-query", user_id="u"), context)
    assert "【方法:gRPC.Chat】" in caplog.records[-1].getMessage()
    assert "【状态:失败】" in caplog.records[-1].getMessage()
    assert "【状态码:INTERNAL】" in caplog.records[-1].getMessage()
    assert "private-error" not in caplog.text

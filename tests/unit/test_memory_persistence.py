from unittest.mock import patch

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

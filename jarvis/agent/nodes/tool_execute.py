import logging

from langchain_core.messages import AIMessage, ToolMessage

from jarvis.agent.state import AgentState
from jarvis.logging_config import format_log_tags
from jarvis.tools.errors import ToolUnavailableError
from jarvis.tools.registry import get_tool_registration


logger = logging.getLogger(__name__)
TOOL_UNAVAILABLE_MESSAGE = (
    "This tool is unavailable. Do not retry it. "
    "Answer directly using existing knowledge and any other tool results."
)


def _unavailable_tool_message(
    tool_name: str,
    tool_call_id: str,
    category: str,
) -> ToolMessage:
    logger.warning(
        "%s Tool unavailable",
        format_log_tags(
            ("节点", "tool_node"),
            ("工具", tool_name),
            ("状态", "降级"),
            ("类别", category),
        ),
    )
    return ToolMessage(
        content=TOOL_UNAVAILABLE_MESSAGE,
        tool_call_id=tool_call_id,
        name=tool_name,
    )


def execute_tools(state: AgentState) -> dict:
    active_tool = "unknown"
    try:
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError("tool execution requires an AIMessage")

        unavailable = set(state.get("unavailable_tools", []))
        messages: list[ToolMessage] = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            active_tool = tool_name
            registration = get_tool_registration(tool_name)
            if registration is None:
                raise ValueError("model requested an unknown tool")

            missing = registration.missing_env_vars()
            if missing or tool_name in unavailable:
                unavailable.add(tool_name)
                messages.append(
                    _unavailable_tool_message(
                        tool_name,
                        tool_call["id"],
                        "configuration",
                    )
                )
                continue

            try:
                result = registration.tool.invoke(tool_call["args"])
            except ToolUnavailableError as error:
                unavailable.add(tool_name)
                messages.append(
                    _unavailable_tool_message(
                        tool_name,
                        tool_call["id"],
                        error.category,
                    )
                )
                continue

            messages.append(
                ToolMessage(
                    content=(
                        result
                        if isinstance(result, (str, list))
                        else str(result)
                    ),
                    tool_call_id=tool_call["id"],
                    name=tool_name,
                )
            )

        return {
            "messages": messages,
            "unavailable_tools": sorted(unavailable),
        }
    except Exception as error:
        logger.error(
            "%s Tool execution failed",
            format_log_tags(
                ("节点", "tool_node"),
                ("工具", active_tool),
                ("状态", "失败"),
                ("错误", type(error).__name__),
            ),
        )
        raise

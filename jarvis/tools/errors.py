class ToolUnavailableError(RuntimeError):
    def __init__(self, tool_name: str, category: str):
        self.tool_name = tool_name
        self.category = category
        super().__init__("tool is unavailable")


def raise_for_tool_status(response, tool_name: str) -> None:
    if response.status_code in {401, 403}:
        raise ToolUnavailableError(tool_name, "credential")
    if 500 <= response.status_code <= 599:
        raise ToolUnavailableError(tool_name, "provider")
    response.raise_for_status()

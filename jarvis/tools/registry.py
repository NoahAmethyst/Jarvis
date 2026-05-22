from typing import Callable
from langchain_core.tools import StructuredTool

_REGISTRY: dict[str, StructuredTool] = {}


def register_tool(name: str, description: str):
    def decorator(func: Callable) -> Callable:
        _REGISTRY[name] = StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
        )
        return func
    return decorator


def get_tools() -> list[StructuredTool]:
    return list(_REGISTRY.values())

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from langchain_core.tools import StructuredTool


@dataclass(frozen=True)
class ToolRegistration:
    tool: StructuredTool
    required_env_vars: tuple[str, ...] = ()

    def missing_env_vars(
        self,
        environ: Mapping[str, str] | None = None,
    ) -> tuple[str, ...]:
        source = os.environ if environ is None else environ
        return tuple(
            name for name in self.required_env_vars if not source.get(name)
        )


_REGISTRY: dict[str, ToolRegistration] = {}


def register_tool(
    name: str,
    description: str,
    required_env_vars: tuple[str, ...] = (),
):
    def decorator(func: Callable) -> Callable:
        tool = StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
        )
        _REGISTRY[name] = ToolRegistration(
            tool=tool,
            required_env_vars=tuple(required_env_vars),
        )
        return func

    return decorator


def get_tool_registrations() -> list[ToolRegistration]:
    return list(_REGISTRY.values())


def get_tool_registration(name: str) -> ToolRegistration | None:
    return _REGISTRY.get(name)


def get_tools(excluded_names: Iterable[str] = ()) -> list[StructuredTool]:
    excluded = set(excluded_names)
    return [
        registration.tool
        for name, registration in _REGISTRY.items()
        if name not in excluded and not registration.missing_env_vars()
    ]

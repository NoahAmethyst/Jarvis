from collections.abc import Sequence
from functools import lru_cache

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from jarvis.llm.config import load_llm_config
from jarvis.llm.gateway import LLMGateway


@lru_cache(maxsize=1)
def get_llm() -> LLMGateway:
    return LLMGateway(load_llm_config())


class _LazyLLM:
    def chat(
        self,
        profile: str,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool] | None = None,
        override: str | None = None,
    ) -> AIMessage:
        return get_llm().chat(
            profile=profile,
            messages=messages,
            tools=tools,
            override=override,
        )


llm = _LazyLLM()

__all__ = ["get_llm", "llm"]

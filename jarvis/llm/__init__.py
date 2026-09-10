from collections.abc import Sequence
from functools import lru_cache
from contextlib import contextmanager
from contextvars import ContextVar

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from jarvis.llm.config import load_llm_config
from jarvis.llm.gateway import LLMGateway
from jarvis.llm import runtime

_request_llm: ContextVar[LLMGateway | None] = ContextVar("request_llm", default=None)


@lru_cache(maxsize=1)
def _base_llm() -> LLMGateway:
    return LLMGateway(load_llm_config())


def get_llm() -> LLMGateway:
    pinned = _request_llm.get()
    if pinned is not None:
        return pinned
    base = _base_llm()
    if not runtime.enabled():
        return base
    _, models = runtime.read_overrides()
    return LLMGateway(runtime.apply_overrides(base.settings, models))


get_llm.cache_clear = _base_llm.cache_clear


@contextmanager
def model_session():
    """Keep tool/reasoning transcripts on one configuration for the entire request."""
    if not runtime.enabled() or _request_llm.get() is not None:
        yield
        return
    token = _request_llm.set(get_llm())
    try:
        yield
    finally:
        _request_llm.reset(token)


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

from typing import Any

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek

from jarvis.llm.adapters.base import BaseAdapter
from jarvis.llm.config import ProviderSettings, ThinkingSettings


class JarvisChatDeepSeek(ChatDeepSeek):
    """Preserve DeepSeek reasoning across tool-call requests."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        source_messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        for source, target in zip(source_messages, payload["messages"], strict=True):
            if not isinstance(source, AIMessage):
                continue
            reasoning_content = source.additional_kwargs.get("reasoning_content")
            if reasoning_content is not None:
                target["reasoning_content"] = reasoning_content
        return payload


class DeepSeekAdapter(BaseAdapter):
    def create_model(
        self,
        provider: ProviderSettings,
        model_id: str,
        thinking: ThinkingSettings,
        request_timeout: float | None = None,
    ) -> BaseChatModel:
        kwargs: dict[str, Any] = {
            "model": model_id,
            "api_key": self.resolve_api_key(provider),
            "base_url": self.resolve_base_url(provider),
            "max_retries": 0,
            "extra_body": {"thinking": {"type": thinking.mode}},
        }
        if request_timeout is not None:
            kwargs["request_timeout"] = request_timeout
        if thinking.mode == "enabled":
            kwargs["reasoning_effort"] = thinking.effort
        return JarvisChatDeepSeek(**kwargs)

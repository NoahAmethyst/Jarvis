from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from jarvis.llm.adapters.base import BaseAdapter
from jarvis.llm.config import ProviderSettings, ThinkingSettings


class OpenAICompatibleAdapter(BaseAdapter):
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
        }
        if request_timeout is not None:
            kwargs["request_timeout"] = request_timeout
        if thinking.mode == "enabled":
            kwargs["reasoning_effort"] = thinking.effort
        return ChatOpenAI(**kwargs)

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from jarvis.llm.adapters.base import BaseAdapter
from jarvis.llm.config import ProviderSettings, ThinkingSettings


class AnthropicAdapter(BaseAdapter):
    def create_model(
        self,
        provider: ProviderSettings,
        model_id: str,
        thinking: ThinkingSettings,
    ) -> BaseChatModel:
        kwargs: dict[str, Any] = {
            "model_name": model_id,
            "api_key": self.resolve_api_key(provider),
            "max_retries": 0,
        }
        base_url = self.resolve_base_url(provider)
        if base_url:
            kwargs["base_url"] = base_url
        if thinking.mode == "enabled":
            kwargs["effort"] = thinking.effort
        return ChatAnthropic(**kwargs)

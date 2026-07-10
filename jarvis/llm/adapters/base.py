import os
from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel

from jarvis.llm.config import ProviderSettings, ThinkingSettings
from jarvis.llm.errors import LLMConfigurationError


class BaseAdapter(ABC):
    def resolve_api_key(self, provider: ProviderSettings) -> str:
        api_key = os.getenv(provider.api_key_env, "")
        if not api_key:
            raise LLMConfigurationError("selected LLM provider is not configured")
        return api_key

    def resolve_base_url(self, provider: ProviderSettings) -> str | None:
        if provider.base_url_env:
            configured = os.getenv(provider.base_url_env, "")
            if configured:
                return configured
        return provider.base_url

    @abstractmethod
    def create_model(
        self,
        provider: ProviderSettings,
        model_id: str,
        thinking: ThinkingSettings,
    ) -> BaseChatModel:
        raise NotImplementedError

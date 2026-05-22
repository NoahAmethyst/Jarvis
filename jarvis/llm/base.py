from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel


class BaseLLMProvider(ABC):
    @abstractmethod
    def get_chat_model(self, model_id: str, **kwargs) -> BaseChatModel: ...

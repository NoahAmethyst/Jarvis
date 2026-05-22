from langchain_anthropic import ChatAnthropic
from jarvis.config import ANTHROPIC_API_KEY
from jarvis.llm.base import BaseLLMProvider
from langchain_core.language_models import BaseChatModel


class ClaudeProvider(BaseLLMProvider):
    def get_chat_model(self, model_id: str, **kwargs) -> BaseChatModel:
        return ChatAnthropic(
            model=model_id,
            api_key=ANTHROPIC_API_KEY,
            **kwargs,
        )

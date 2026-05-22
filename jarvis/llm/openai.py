from langchain_openai import ChatOpenAI
from jarvis.config import OPENAI_API_KEY
from jarvis.llm.base import BaseLLMProvider
from langchain_core.language_models import BaseChatModel


class OpenAIProvider(BaseLLMProvider):
    def get_chat_model(self, model_id: str, **kwargs) -> BaseChatModel:
        return ChatOpenAI(
            model=model_id,
            api_key=OPENAI_API_KEY,
            **kwargs,
        )

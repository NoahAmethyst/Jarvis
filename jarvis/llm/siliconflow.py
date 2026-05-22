from langchain_openai import ChatOpenAI
from jarvis.config import SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL
from jarvis.llm.base import BaseLLMProvider
from langchain_core.language_models import BaseChatModel


class SiliconFlowProvider(BaseLLMProvider):
    def get_chat_model(self, model_id: str, **kwargs) -> BaseChatModel:
        return ChatOpenAI(
            model=model_id,
            api_key=SILICONFLOW_API_KEY,
            base_url=SILICONFLOW_BASE_URL,
            **kwargs,
        )

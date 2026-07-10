from jarvis.llm.adapters.anthropic import AnthropicAdapter
from jarvis.llm.adapters.base import BaseAdapter
from jarvis.llm.adapters.deepseek import DeepSeekAdapter
from jarvis.llm.adapters.openai_compatible import OpenAICompatibleAdapter
from jarvis.llm.config import AdapterName


ADAPTERS: dict[AdapterName, BaseAdapter] = {
    "deepseek": DeepSeekAdapter(),
    "openai_compatible": OpenAICompatibleAdapter(),
    "anthropic": AnthropicAdapter(),
}

__all__ = ["ADAPTERS", "BaseAdapter"]

"""Deprecated raw-model router kept for external compatibility.

Production Jarvis callers use the profile gateway exposed as `jarvis.llm.llm`.
"""

import logging
from langchain_core.language_models import BaseChatModel
from jarvis.llm.siliconflow import SiliconFlowProvider
from jarvis.llm.openai import OpenAIProvider
from jarvis.llm.claude import ClaudeProvider

logger = logging.getLogger(__name__)

REGISTRY: dict = {
    "siliconflow": SiliconFlowProvider(),
    "openai": OpenAIProvider(),
    "claude": ClaudeProvider(),
}


class ProviderNotFoundError(ValueError):
    pass


class ProviderUnavailableError(RuntimeError):
    pass


def get_model(model_spec: str, **kwargs) -> BaseChatModel:
    """Return a raw legacy model; new code must use `llm.chat()` instead."""
    parts = model_spec.split("/", 1)
    if len(parts) != 2:
        logger.error(f"Invalid model spec: {model_spec}")
        raise ProviderNotFoundError("provider not exist")

    provider_name, model_id = parts
    if provider_name not in REGISTRY:
        logger.error(f"Provider not found: {provider_name}")
        raise ProviderNotFoundError("provider not exist")

    try:
        return REGISTRY[provider_name].get_chat_model(model_id=model_id, **kwargs)
    except (ProviderNotFoundError, ProviderUnavailableError):
        raise
    except Exception as e:
        logger.error(f"Provider unavailable: {provider_name}, reason: {e}")
        raise ProviderUnavailableError(f"provider not working:{e}")

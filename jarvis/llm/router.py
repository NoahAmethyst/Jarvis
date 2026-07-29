"""Deprecated raw-model router kept for external compatibility.

Production Jarvis callers use the profile gateway exposed as `jarvis.llm.llm`.
"""

import logging
from langchain_core.language_models import BaseChatModel
from jarvis.llm.siliconflow import SiliconFlowProvider
from jarvis.llm.openai import OpenAIProvider
from jarvis.llm.claude import ClaudeProvider
from jarvis.logging_config import format_log_tags

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
        logger.error(
            "%s Invalid model specification",
            format_log_tags(
                ("组件", "LLM路由"),
                ("结果", "失败"),
                ("类别", "configuration"),
            ),
        )
        raise ProviderNotFoundError("provider not exist")

    provider_name, model_id = parts
    if provider_name not in REGISTRY:
        logger.error(
            "%s Provider not found",
            format_log_tags(
                ("组件", "LLM路由"),
                ("供应商", provider_name),
                ("结果", "失败"),
                ("类别", "configuration"),
            ),
        )
        raise ProviderNotFoundError("provider not exist")

    try:
        return REGISTRY[provider_name].get_chat_model(model_id=model_id, **kwargs)
    except (ProviderNotFoundError, ProviderUnavailableError):
        raise
    except Exception as error:
        logger.error(
            "%s Provider unavailable",
            format_log_tags(
                ("组件", "LLM路由"),
                ("供应商", provider_name),
                ("模型", model_id),
                ("结果", "失败"),
                ("错误", type(error).__name__),
            ),
        )
        raise ProviderUnavailableError(f"provider not working:{error}")

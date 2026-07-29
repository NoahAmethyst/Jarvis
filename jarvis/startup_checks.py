import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import anthropic
import openai
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, HumanMessage

from jarvis.config import EMBED_MODEL
from jarvis.llm.adapters import ADAPTERS
from jarvis.llm.adapters.base import BaseAdapter
from jarvis.llm.config import (
    LLMSettings,
    ThinkingSettings,
    load_llm_config,
    parse_model_spec,
)
from jarvis.llm.errors import (
    LLMConfigurationError,
    LLMCredentialError,
    LLMInvalidResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from jarvis.logging_config import format_log_tags
from jarvis.memory.knowledge import _get_embeddings, _parse_embed_model


logger = logging.getLogger(__name__)
STARTUP_CHECK_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class ChatTarget:
    provider_name: str
    model_id: str


def discover_active_chat_targets(settings: LLMSettings) -> list[ChatTarget]:
    targets: list[ChatTarget] = []
    seen: set[str] = set()
    for profile in settings.profiles.values():
        provider_name, model_id = parse_model_spec(profile.model)
        if provider_name in seen:
            continue
        seen.add(provider_name)
        targets.append(ChatTarget(provider_name, model_id))
    return targets


def failure_category(error: Exception) -> str:
    if getattr(error, "status_code", None) in {401, 403}:
        return "credential"
    if isinstance(error, LLMCredentialError):
        return "credential"
    if isinstance(error, LLMConfigurationError):
        return "configuration"
    if isinstance(
        error,
        (LLMTimeoutError, openai.APITimeoutError, anthropic.APITimeoutError),
    ):
        return "timeout"
    if isinstance(
        error,
        (
            LLMUnavailableError,
            openai.APIConnectionError,
            anthropic.APIConnectionError,
        ),
    ):
        return "connectivity"
    return "provider"


def check_chat_providers(
    settings: LLMSettings,
    adapters: Mapping[str, BaseAdapter] | None = None,
) -> None:
    adapter_registry = adapters or ADAPTERS
    thinking = ThinkingSettings(mode="disabled")
    messages = [HumanMessage(content="Reply with OK.")]

    for target in discover_active_chat_targets(settings):
        try:
            provider = settings.providers[target.provider_name]
            adapter = adapter_registry[provider.adapter]
            model = adapter.create_model(
                provider,
                target.model_id,
                thinking,
                request_timeout=STARTUP_CHECK_TIMEOUT_SECONDS,
            )
            response = model.invoke(messages)
            if not isinstance(response, AIMessage):
                raise LLMInvalidResponseError(
                    "LLM provider returned an invalid response"
                )
        except Exception as error:
            logger.error(
                "%s Startup connectivity check failed",
                format_log_tags(
                    ("供应商", target.provider_name),
                    ("模型", target.model_id),
                    ("类型", "Chat"),
                    ("结果", "失败"),
                    ("类别", failure_category(error)),
                ),
            )
            continue
        logger.info(
            "%s Startup connectivity check completed",
            format_log_tags(
                ("供应商", target.provider_name),
                ("模型", target.model_id),
                ("类型", "Chat"),
                ("结果", "成功"),
            ),
        )


def check_embedding_model(
    model_spec: str = EMBED_MODEL,
    embeddings_factory: Callable[[], Embeddings] | None = None,
) -> None:
    try:
        provider_name, model_id, _ = _parse_embed_model(model_spec)
    except Exception as error:
        logger.error(
            "%s Startup connectivity check failed",
            format_log_tags(
                ("供应商", "unknown"),
                ("模型", "unknown"),
                ("类型", "Embedding"),
                ("结果", "失败"),
                ("类别", failure_category(error)),
            ),
        )
        return
    try:
        embeddings = (
            embeddings_factory()
            if embeddings_factory is not None
            else _get_embeddings(
                model_spec=model_spec,
                request_timeout=STARTUP_CHECK_TIMEOUT_SECONDS,
                max_retries=0,
            )
        )
        embeddings.embed_query("Jarvis startup connectivity check")
    except Exception as error:
        logger.error(
            "%s Startup connectivity check failed",
            format_log_tags(
                ("供应商", provider_name),
                ("模型", model_id),
                ("类型", "Embedding"),
                ("结果", "失败"),
                ("类别", failure_category(error)),
            ),
        )
        return
    logger.info(
        "%s Startup connectivity check completed",
        format_log_tags(
            ("供应商", provider_name),
            ("模型", model_id),
            ("类型", "Embedding"),
            ("结果", "成功"),
        ),
    )


def run_model_startup_checks(
    settings_loader: Callable[[], LLMSettings] | None = None,
    adapters: Mapping[str, BaseAdapter] | None = None,
    embeddings_factory: Callable[[], Embeddings] | None = None,
    embedding_model_spec: str = EMBED_MODEL,
) -> None:
    loader = settings_loader or load_llm_config
    try:
        settings = loader()
    except Exception as error:
        logger.error(
            "%s Could not load active provider configuration",
            format_log_tags(
                ("供应商", "unknown"),
                ("模型", "unknown"),
                ("类型", "Chat"),
                ("结果", "失败"),
                ("类别", failure_category(error)),
            ),
        )
    else:
        check_chat_providers(settings, adapters=adapters)

    check_embedding_model(
        embedding_model_spec,
        embeddings_factory=embeddings_factory,
    )

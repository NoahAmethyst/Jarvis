import logging
import os
from collections.abc import Callable, Iterable, Mapping
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
from jarvis.tools.registry import (
    ToolRegistration,
    get_tool_registrations,
)


logger = logging.getLogger(__name__)
STARTUP_CHECK_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class ChatTarget:
    provider_name: str
    model_id: str


@dataclass(frozen=True)
class CredentialTarget:
    component: str
    component_type: str
    env_var: str


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


def _embedding_credential_target(
    model_spec: str,
) -> CredentialTarget | None:
    try:
        provider_name, _, _ = _parse_embed_model(model_spec)
    except Exception:
        return None
    env_vars = {
        "siliconflow": "SILICONFLOW_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    env_var = env_vars.get(provider_name)
    if env_var is None:
        return None
    return CredentialTarget(provider_name, "Embedding", env_var)


def discover_credential_targets(
    settings: LLMSettings | None,
    embedding_model_spec: str,
    tool_registrations: Iterable[ToolRegistration] | None = None,
) -> list[CredentialTarget]:
    targets: list[CredentialTarget] = []
    if settings is not None:
        for chat_target in discover_active_chat_targets(settings):
            provider = settings.providers[chat_target.provider_name]
            targets.append(
                CredentialTarget(
                    chat_target.provider_name,
                    "Chat",
                    provider.api_key_env,
                )
            )

    embedding_target = _embedding_credential_target(embedding_model_spec)
    if embedding_target is not None:
        targets.append(embedding_target)

    registrations = (
        get_tool_registrations()
        if tool_registrations is None
        else tool_registrations
    )
    for registration in registrations:
        targets.extend(
            CredentialTarget(
                registration.tool.name,
                "Tool",
                env_var,
            )
            for env_var in registration.required_env_vars
        )

    unique: list[CredentialTarget] = []
    seen: set[CredentialTarget] = set()
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        unique.append(target)
    return unique


def check_required_credentials(
    settings: LLMSettings | None,
    embedding_model_spec: str,
    tool_registrations: Iterable[ToolRegistration] | None = None,
    environ: Mapping[str, str] | None = None,
) -> set[str]:
    source = os.environ if environ is None else environ
    missing: set[str] = set()
    for target in discover_credential_targets(
        settings,
        embedding_model_spec,
        tool_registrations=tool_registrations,
    ):
        configured = bool(source.get(target.env_var))
        if not configured:
            missing.add(target.env_var)
        log = logger.info if configured else logger.warning
        log(
            "%s Required credential %s",
            format_log_tags(
                ("组件", target.component),
                ("类型", target.component_type),
                ("配置", target.env_var),
                ("状态", "已配置" if configured else "未配置"),
            ),
            "is configured" if configured else "is not configured",
        )
    return missing


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
    missing_env_vars: Iterable[str] = (),
) -> None:
    adapter_registry = adapters or ADAPTERS
    missing = set(missing_env_vars)
    thinking = ThinkingSettings(mode="disabled")
    messages = [HumanMessage(content="Reply with OK.")]

    for target in discover_active_chat_targets(settings):
        provider = settings.providers[target.provider_name]
        if provider.api_key_env in missing:
            continue
        try:
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
    missing_env_vars: Iterable[str] = (),
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
    credential_target = _embedding_credential_target(model_spec)
    if (
        credential_target is not None
        and credential_target.env_var in set(missing_env_vars)
    ):
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
    settings: LLMSettings | None = None
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
    missing_env_vars = check_required_credentials(
        settings,
        embedding_model_spec,
    )

    if settings is not None:
        check_chat_providers(
            settings,
            adapters=adapters,
            missing_env_vars=missing_env_vars,
        )

    check_embedding_model(
        embedding_model_spec,
        embeddings_factory=embeddings_factory,
        missing_env_vars=missing_env_vars,
    )

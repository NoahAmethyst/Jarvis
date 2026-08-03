import logging
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import anthropic
import openai
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool

from jarvis.llm.adapters import ADAPTERS
from jarvis.llm.adapters.base import BaseAdapter
from jarvis.llm.config import LLMSettings, ProfileSettings, ThinkingSettings, parse_model_spec
from jarvis.llm.errors import (
    LLMConfigurationError,
    LLMContextLimitError,
    LLMError,
    LLMInvalidRequestError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from jarvis.logging_config import format_log_tags, sanitize_log_value


logger = logging.getLogger(__name__)

TRANSIENT_ERRORS = (LLMRateLimitError, LLMTimeoutError, LLMUnavailableError)


def _provider_error_status(error: Exception) -> int | None:
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _provider_error_detail(error: Exception) -> str:
    body = getattr(error, "body", None)
    if isinstance(body, Mapping):
        nested_error = body.get("error")
        if isinstance(nested_error, Mapping):
            message = nested_error.get("message")
            if message:
                return sanitize_log_value(message)
        message = body.get("message")
        if message:
            return sanitize_log_value(message)
    if body:
        return sanitize_log_value(body)
    return sanitize_log_value(error)


class LLMGateway:
    def __init__(
        self,
        settings: LLMSettings,
        adapters: Mapping[str, BaseAdapter] | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        self.settings = settings
        self.adapters = dict(adapters or ADAPTERS)
        self.sleep = sleep if sleep is not None else time.sleep

    def chat(
        self,
        profile: str,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool] | None = None,
        override: str | None = None,
    ) -> AIMessage:
        profile_settings = self.settings.profiles.get(profile)
        if profile_settings is None:
            raise LLMInvalidRequestError("unknown LLM profile")

        model_spec = override or profile_settings.model
        provider_name, model_id = parse_model_spec(model_spec)
        provider = self.settings.providers.get(provider_name)
        if provider is None:
            raise LLMInvalidRequestError("unknown LLM provider")

        adapter = self.adapters.get(provider.adapter)
        if adapter is None:
            raise LLMConfigurationError("selected LLM adapter is not configured")

        thinking = self._resolve_thinking(
            profile_settings=profile_settings,
            provider_supports_thinking=provider.capabilities.thinking,
            is_override=override is not None,
            provider_name=provider_name,
            model_id=model_id,
        )
        if profile_settings.tools == "enabled" and not provider.capabilities.tools:
            raise LLMInvalidRequestError("selected LLM does not support required tool capability")

        prepared_messages = self._prepare_messages(
            messages=list(messages),
            max_messages=provider.limits.max_messages,
        )
        if provider.adapter == "deepseek" and thinking.mode == "enabled":
            self._validate_deepseek_reasoning_input(prepared_messages)

        return self._invoke(
            adapter=adapter,
            provider=provider,
            provider_name=provider_name,
            model_id=model_id,
            profile=profile_settings,
            thinking=thinking,
            messages=prepared_messages,
            tools=list(tools or []),
        )

    def _resolve_thinking(
        self,
        profile_settings: ProfileSettings,
        provider_supports_thinking: bool,
        is_override: bool,
        provider_name: str,
        model_id: str,
    ) -> ThinkingSettings:
        thinking = profile_settings.thinking.model_copy(deep=True)
        if thinking.mode == "disabled" or provider_supports_thinking:
            return thinking
        if is_override and thinking.on_unsupported == "disable":
            logger.info(
                "%s Unsupported thinking disabled for override",
                format_log_tags(
                    ("供应商", provider_name),
                    ("模型", model_id),
                    ("状态", "降级"),
                ),
            )
            return thinking.model_copy(update={"mode": "disabled", "effort": None})
        raise LLMInvalidRequestError("selected LLM does not support required thinking capability")

    def _prepare_messages(
        self,
        messages: list[BaseMessage],
        max_messages: int | None,
    ) -> list[BaseMessage]:
        groups = self._group_messages(messages)
        if max_messages is None or len(messages) <= max_messages:
            return messages

        last_human_group: int | None = None
        mandatory_groups: set[int] = set()
        for index, group in enumerate(groups):
            if any(isinstance(message, SystemMessage) for message in group):
                mandatory_groups.add(index)
            if any(isinstance(message, HumanMessage) for message in group):
                last_human_group = index
        if last_human_group is not None:
            mandatory_groups.update(range(last_human_group, len(groups)))

        mandatory_count = sum(len(groups[index]) for index in mandatory_groups)
        if mandatory_count > max_messages:
            raise LLMContextLimitError("LLM context limit exceeded")

        keep = [True] * len(groups)
        current_count = len(messages)
        for index, group in enumerate(groups):
            if current_count <= max_messages:
                break
            if index in mandatory_groups:
                continue
            keep[index] = False
            current_count -= len(group)

        if current_count > max_messages:
            raise LLMContextLimitError("LLM context limit exceeded")
        return [
            message
            for index, group in enumerate(groups)
            if keep[index]
            for message in group
        ]

    def _group_messages(self, messages: list[BaseMessage]) -> list[list[BaseMessage]]:
        groups: list[list[BaseMessage]] = []
        seen_tool_call_ids: set[str] = set()
        index = 0
        while index < len(messages):
            message = messages[index]
            if isinstance(message, ToolMessage):
                raise LLMInvalidRequestError("invalid tool message sequence")
            if not isinstance(message, AIMessage) or not message.tool_calls:
                groups.append([message])
                index += 1
                continue

            tool_call_ids = [call.get("id") for call in message.tool_calls]
            if (
                any(not tool_call_id for tool_call_id in tool_call_ids)
                or len(set(tool_call_ids)) != len(tool_call_ids)
                or any(tool_call_id in seen_tool_call_ids for tool_call_id in tool_call_ids)
            ):
                raise LLMInvalidRequestError("invalid tool message sequence")

            expected_ids = set(tool_call_ids)
            seen_tool_call_ids.update(expected_ids)
            group: list[BaseMessage] = [message]
            result_ids: set[str] = set()
            index += 1
            while index < len(messages) and isinstance(messages[index], ToolMessage):
                tool_message = messages[index]
                if (
                    tool_message.tool_call_id not in expected_ids
                    or tool_message.tool_call_id in result_ids
                ):
                    raise LLMInvalidRequestError("invalid tool message sequence")
                result_ids.add(tool_message.tool_call_id)
                group.append(tool_message)
                index += 1
            if result_ids != expected_ids:
                raise LLMInvalidRequestError("invalid tool message sequence")
            groups.append(group)
        return groups

    def _validate_deepseek_reasoning_input(self, messages: Sequence[BaseMessage]) -> None:
        for message in messages:
            if not isinstance(message, AIMessage) or not message.tool_calls:
                continue
            if not message.additional_kwargs.get("reasoning_content"):
                raise LLMInvalidRequestError("DeepSeek tool call is missing reasoning content")

    def _invoke(
        self,
        *,
        adapter: BaseAdapter,
        provider,
        provider_name: str,
        model_id: str,
        profile: ProfileSettings,
        thinking: ThinkingSettings,
        messages: list[BaseMessage],
        tools: list[BaseTool],
    ) -> AIMessage:
        for attempt in range(profile.retry.max_attempts):
            try:
                model = adapter.create_model(provider, model_id, thinking)
                runnable = (
                    model.bind_tools(tools)
                    if profile.tools == "enabled" and tools
                    else model
                )
                response = runnable.invoke(messages)
                if not isinstance(response, AIMessage):
                    raise LLMInvalidResponseError(
                        "LLM provider returned an invalid response"
                    )
                if (
                    provider.adapter == "deepseek"
                    and thinking.mode == "enabled"
                    and response.tool_calls
                    and not response.additional_kwargs.get("reasoning_content")
                ):
                    raise LLMInvalidResponseError(
                        "LLM provider returned an invalid response"
                    )
                return response
            except Exception as error:
                normalized = normalize_provider_error(error)
                detail_fields = [("归一化", type(normalized).__name__)]
                status_code = _provider_error_status(error)
                if status_code is not None:
                    detail_fields.append(("状态码", status_code))
                logger.warning(
                    "%s LLM request failed %s detail=%s",
                    format_log_tags(
                        ("供应商", provider_name),
                        ("模型", model_id),
                        ("结果", "失败"),
                        ("错误", type(error).__name__),
                    ),
                    format_log_tags(*detail_fields),
                    _provider_error_detail(error),
                )
                if (
                    isinstance(normalized, TRANSIENT_ERRORS)
                    and attempt + 1 < profile.retry.max_attempts
                ):
                    delay = profile.retry.base_delay_seconds * (2**attempt)
                    self.sleep(delay)
                    continue
                if normalized is error:
                    raise
                raise normalized from error
        raise LLMUnavailableError("LLM provider unavailable")


def normalize_provider_error(error: Exception) -> LLMError:
    if isinstance(error, LLMError):
        return error
    if isinstance(error, (openai.RateLimitError, anthropic.RateLimitError)):
        return LLMRateLimitError("LLM rate limit exceeded")
    if isinstance(error, (openai.APITimeoutError, anthropic.APITimeoutError)):
        return LLMTimeoutError("LLM request timed out")
    if isinstance(error, (openai.BadRequestError, anthropic.BadRequestError)):
        return LLMInvalidRequestError("invalid LLM request")
    if isinstance(error, (openai.APIConnectionError, anthropic.APIConnectionError)):
        return LLMUnavailableError("LLM provider unavailable")
    if isinstance(error, (openai.APIStatusError, anthropic.APIStatusError)):
        if error.status_code == 429:
            return LLMRateLimitError("LLM rate limit exceeded")
        if error.status_code >= 500:
            return LLMUnavailableError("LLM provider unavailable")
        return LLMInvalidRequestError("invalid LLM request")
    if isinstance(error, ValueError):
        return LLMConfigurationError("selected LLM provider is not configured")
    return LLMUnavailableError("LLM provider unavailable")

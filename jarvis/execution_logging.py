"""Request-scoped execution events containing metadata rather than content."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter
from uuid import uuid4

from jarvis.config import REFLECTION_SCORE_THRESHOLD
from jarvis.logging_config import NODE_NAME, REQUEST_ID, format_log_tags


logger = logging.getLogger(__name__)
_NODE_FEEDBACK = ContextVar("jarvis_node_feedback", default=None)
_REQUEST_FEEDBACK = ContextVar("jarvis_request_feedback", default=None)


def node_feedback(**fields) -> None:
    feedback = _NODE_FEEDBACK.get()
    if feedback is not None:
        feedback.update(fields)


@contextmanager
def action_trace(action: str, **fields):
    """Allow callers to report counts and outcomes after the action executes."""
    started = perf_counter()
    logger.info(
        "%s", format_log_tags(("动作", action), ("状态", "开始"), *fields.items())
    )
    feedback = {}
    try:
        yield feedback
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            feedback["状态码"] = status_code
        logger.error(
            "%s", format_log_tags(
                ("动作", action), ("状态", "失败"), ("错误", type(error).__name__),
                ("耗时ms", f"{(perf_counter() - started) * 1000:.1f}"), *fields.items(),
                *((name, value) for name, value in feedback.items() if name != "状态"),
            )
        )
        raise
    else:
        status = feedback.pop("状态", "完成")
        level = logging.WARNING if status in {"降级", "失败"} else logging.INFO
        logger.log(
            level, "%s", format_log_tags(
                ("动作", action), ("状态", status),
                ("耗时ms", f"{(perf_counter() - started) * 1000:.1f}"),
                *fields.items(), *feedback.items(),
            )
        )


@contextmanager
def request_trace(method: str):
    token = REQUEST_ID.set(uuid4().hex)
    node_token = NODE_NAME.set(None)
    try:
        with action_trace("请求", 方法=method) as feedback:
            feedback.update(节点执行次数=0, 降级节点数=0)
            feedback_token = _REQUEST_FEEDBACK.set(feedback)
            try:
                yield feedback
            finally:
                _REQUEST_FEEDBACK.reset(feedback_token)
    finally:
        NODE_NAME.reset(node_token)
        REQUEST_ID.reset(token)


def traced_request(method: str, *, grpc: bool = False):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            with request_trace(method) as feedback:
                result = function(*args, **kwargs)
                if grpc:
                    context = args[2] if len(args) > 2 else kwargs["context"]
                    code = getattr(context, "code", None)
                    code = code() if callable(code) else code
                    if code is not None and getattr(code, "name", None) != "OK":
                        feedback.update(状态="失败", 状态码=getattr(code, "name", "error"))
                answer = getattr(result, "answer", getattr(result, "text", None))
                if answer is not None:
                    feedback["回答字符数"] = len(answer)
                if hasattr(result, "low_confidence"):
                    feedback["低置信度"] = result.low_confidence
                return result
        return run
    return decorate


def traced_node(name: str):
    def decorate(function):
        @wraps(function)
        def run(state, *args, **kwargs):
            token = NODE_NAME.set(name)
            try:
                with action_trace("执行节点", 节点=name) as feedback:
                    request_feedback = _REQUEST_FEEDBACK.get()
                    if request_feedback is not None:
                        request_feedback["节点执行次数"] += 1
                    feedback_token = _NODE_FEEDBACK.set(feedback)
                    try:
                        result = function(state, *args, **kwargs)
                    finally:
                        _NODE_FEEDBACK.reset(feedback_token)
                    if name == "memory_load":
                        feedback["历史条数"] = len(result.get("history", []))
                    elif name == "agent_dispatch":
                        agent = result.get("active_agent")
                        feedback.setdefault("状态", "完成" if agent else "跳过")
                        feedback.update(
                            Agent=agent.name if agent else "none",
                            评分=f"{result.get('agent_dispatch_score', 0):.2f}",
                        )
                    elif name == "rag_retrieve":
                        context = result.get("rag_context", "")
                        feedback.update(
                            知识字符数=len(context), 结果="有上下文" if context else "无上下文"
                        )
                    elif name == "plan_and_call":
                        message = result["messages"][-1]
                        calls = getattr(message, "tool_calls", [])
                        feedback.update(
                            工具调用数=len(calls), 决策="调用工具" if calls else "返回回答",
                            回答字符数=len(message.content),
                        )
                    elif name == "reflect":
                        score = result["reflection_score"]
                        feedback.update(
                            评分=f"{score:.2f}", 阈值=REFLECTION_SCORE_THRESHOLD,
                            轮次=result["retry_count"], 低置信度=result["low_confidence"],
                            结果="通过" if score >= REFLECTION_SCORE_THRESHOLD else "未通过",
                        )
                    elif name == "tool_node":
                        feedback.update(
                            返回工具消息数=len(result.get("messages", [])),
                            不可用工具数=len(result.get("unavailable_tools", [])),
                        )
                    if feedback.get("状态") == "降级" and request_feedback is not None:
                        request_feedback["降级节点数"] += 1
                    return result
            finally:
                NODE_NAME.reset(token)
        return run
    return decorate

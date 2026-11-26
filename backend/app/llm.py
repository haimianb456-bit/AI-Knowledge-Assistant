"""兼容 OpenAI Chat Completions 格式的模型服务调用封装，支持普通及 SSE 流式输出。"""
import json
from collections.abc import AsyncIterator

import httpx

from .config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT,
    SYSTEM_PROMPT,
)


class LLMConfigError(Exception):
    """模型服务配置错误。"""


class LLMRequestError(Exception):
    """模型服务请求错误。"""


def _build_messages(history: list[dict[str, str]], user_content: str, system_context: str = "") -> list[dict[str, str]]:
    system_content = SYSTEM_PROMPT
    if system_context:
        system_content += "\n\n" + system_context
    messages = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages


def _headers() -> dict[str, str]:
    if not LLM_API_KEY:
        raise LLMConfigError("尚未配置模型 API Key。请在 backend/.env 中填写 LLM_API_KEY。")
    return {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}


def _error_message(status_code: int, body: str) -> str:
    try:
        error_data = json.loads(body)
        error_info = error_data.get("error") if isinstance(error_data, dict) else None
        if isinstance(error_info, dict):
            detail = error_info.get("message") or error_info.get("code")
        elif isinstance(error_info, str):
            detail = error_info
        else:
            detail = None
    except (ValueError, TypeError):
        detail = None
    return f"模型服务返回错误（HTTP {status_code}）：{detail or f'{LLM_PROVIDER} 服务暂时无法处理请求'}"


async def create_answer(history: list[dict[str, str]], user_content: str, system_context: str = "") -> str:
    payload = {
        "model": LLM_MODEL,
        "messages": _build_messages(history, user_content, system_context),
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            response = await client.post(
                f"{LLM_BASE_URL}/chat/completions", json=payload, headers=_headers()
            )
        if response.status_code >= 400:
            raise LLMRequestError(_error_message(response.status_code, response.text))
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise LLMRequestError("模型响应中没有 choices 字段，请检查模型服务返回内容。")
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMRequestError("模型返回内容为空。请确认所选模型支持 Chat Completions 文本对话。")
        return content.strip()
    except httpx.TimeoutException as exc:
        raise LLMRequestError(f"请求 {LLM_PROVIDER} 超时，请稍后重试。") from exc
    except httpx.RequestError as exc:
        raise LLMRequestError(f"无法连接 {LLM_PROVIDER} 服务，请检查网络后重试。") from exc


async def stream_answer(
    history: list[dict[str, str]], user_content: str, system_context: str = ""
) -> AsyncIterator[str]:
    """逐段产出模型文本；遇到上游错误时抛出 LLMRequestError。"""
    payload = {
        "model": LLM_MODEL,
        "messages": _build_messages(history, user_content, system_context),
        "stream": True,
    }
    timeout = httpx.Timeout(LLM_TIMEOUT, connect=20.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{LLM_BASE_URL}/chat/completions",
                json=payload,
                headers=_headers(),
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise LLMRequestError(_error_message(response.status_code, body.decode("utf-8", "replace")))

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        break
                    try:
                        data = json.loads(data_text)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices", []) if isinstance(data, dict) else []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}) or {}
                    piece = delta.get("content")
                    if isinstance(piece, str) and piece:
                        yield piece
    except httpx.TimeoutException as exc:
        raise LLMRequestError(f"请求 {LLM_PROVIDER} 超时，请稍后重试。") from exc
    except httpx.RequestError as exc:
        raise LLMRequestError(f"无法连接 {LLM_PROVIDER} 服务，请检查网络后重试。") from exc

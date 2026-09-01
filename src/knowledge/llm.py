"""轻量 DeepSeek LLM 客户端（OpenAI-compatible），用于结构化 JSON 输出。

与 LangChain 无关 —— 直接调用 openai SDK + ``response_format={"type": "json_object"}``
强制结构化输出，供 arxiv_ingest 的双射提取等场景使用。

用法::

    from src.knowledge.llm import chat_json

    data = chat_json(
        system="你是组合数学助手。",
        user="从下面段落提取双射信息，输出 JSON。\n\n...",
    )
    # data -> dict
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from src.config import get_config

logger = logging.getLogger(__name__)

# 默认模型：pro 推理更强，适合数学提取；可被 LLM_MODEL 覆盖
DEFAULT_MODEL = "deepseek-v4-pro"


class LLMError(Exception):
    """LLM 调用/解析失败。"""


def _client():
    from openai import OpenAI

    cfg = get_config()
    key = cfg.deepseek_api_key
    if not key:
        raise LLMError("DEEPSEEK_API_KEY not set in .env")
    return OpenAI(api_key=key, base_url="https://api.deepseek.com/v1")


def chat_json(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    retries: int = 1,
    parse_json: Callable[[str], dict] = None,
) -> dict:
    """调用 DeepSeek 并强制返回 JSON 对象。

    Parameters
    ----------
    system:
        System prompt（角色设定、输出规范）。
    user:
        User prompt（待处理内容）。
    model:
        DeepSeek 模型名，默认 deepseek-v4-pro。
    temperature:
        采样温度（数学任务偏低，默认 0.2）。
    max_tokens:
        单次输出上限。None（默认）表示不设上限、交给 API 默认，避免长输出被截断。
    retries:
        失败重试次数（网络/解析错误，默认 1 次）。
    parse_json:
        自定义 JSON 解析器；默认 `json.loads`（对代码块包裹做容错）。

    Returns
    -------
    解析后的 dict。

    Raises
    ------
    LLMError:
        重试耗尽仍失败。
    """
    client = _client()
    last_exc: Optional[Exception] = None
    parser = parse_json or _default_parse_json

    for attempt in range(retries + 1):
        try:
            create_kwargs = {
                "model": model,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            if max_tokens is not None:
                create_kwargs["max_tokens"] = max_tokens
            resp = client.chat.completions.create(**create_kwargs)
            content = resp.choices[0].message.content or ""
            return parser(content)
        except Exception as exc:  # 网络错误、JSON 解析错误等
            last_exc = exc
            logger.warning("chat_json attempt %d failed: %s", attempt + 1, exc)
            if attempt < retries:
                continue
    raise LLMError(f"DeepSeek JSON 调用失败（{retries + 1} 次尝试）: {last_exc}")


def _default_parse_json(content: str) -> dict:
    """解析 LLM 返回的 JSON，兼容被 markdown 代码块包裹的情况。"""
    text = content.strip()
    # 去掉 ```json ... ``` 包裹
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 兜底：截取第一个 { 到最后一个 }
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            data = json.loads(text[start : end + 1])
        else:
            raise
    if not isinstance(data, dict):
        raise ValueError("LLM 返回的不是 JSON 对象")
    return data

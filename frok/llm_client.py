"""
Frok LLM 客户端
统一的大模型调用逻辑，支持 OpenAI 和 Anthropic 格式
"""

import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# ==================== 思考过程过滤 ====================

# 匹配各种模型的思考过程标签
_THINK_PATTERNS = [
    re.compile(r'<think>[\s\S]*?</think>', re.DOTALL),       # DeepSeek / MiMo
    re.compile(r'<analysis>[\s\S]*?</analysis>', re.DOTALL),  # 某些模型
    re.compile(r'<reasoning>[\s\S]*?</reasoning>', re.DOTALL),
    re.compile(r'<scratch>[\s\S]*?</scratch>', re.DOTALL),
]


def strip_thinking(text: str) -> Tuple[str, str]:
    """
    从模型输出中剥离思考过程

    Returns:
        (clean_text, thinking_summary) — 过滤后的文本 + 思考摘要（用于日志）
    """
    thinking_parts = []
    clean = text

    for pattern in _THINK_PATTERNS:
        for match in pattern.finditer(clean):
            thinking_parts.append(match.group().strip())
        clean = pattern.sub('', clean)

    # 清理多余空行
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()

    summary = ""
    if thinking_parts:
        # 取第一个思考块的前100字作为摘要
        first = thinking_parts[0]
        # 去掉标签
        inner = re.sub(r'</?[^>]+>', '', first).strip()
        summary = inner[:100] + ("..." if len(inner) > 100 else "")

    return clean, summary


# ==================== LLM 客户端 ====================

class LLMClient:
    """
    统一的 LLM 调用客户端

    支持:
    - OpenAI 兼容格式（OpenAI、DeepSeek、MiMo、阿里云）
    - Anthropic 格式（Claude）
    """

    def __init__(self, provider_name: str, provider_config: Dict, config: Dict):
        self.provider_name = provider_name
        self.provider_config = provider_config
        self.config = config

    def call(self, messages: List[Dict], stream: bool = True, silent: bool = False) -> Tuple[str, bool]:
        """
        调用大模型

        Args:
            messages: 对话消息
            stream: 是否流式输出
            silent: 静默模式（不打印输出，用于重试）

        Returns:
            (response_text, truncated)
        """
        try:
            if self.provider_name == "anthropic":
                return self._call_anthropic(messages, stream, silent)
            else:
                return self._call_openai(messages, stream, silent)
        except Exception as e:
            logger.exception("LLM 调用失败")
            return f"[错误] 调用失败: {e}", False

    def _call_openai(self, messages: List[Dict], stream: bool, silent: bool = False) -> Tuple[str, bool]:
        from openai import OpenAI
        client = OpenAI(
            api_key=self.provider_config["api_key"],
            base_url=self.provider_config.get("base_url")
        )
        response = client.chat.completions.create(
            model=self.provider_config["default_model"],
            messages=messages,
            max_tokens=self.config.get("max_tokens", 16384),
            temperature=self.config.get("temperature", 0.7),
            stream=stream
        )
        if stream:
            full_response = ""
            truncated = False
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        full_response += delta.content
                    if chunk.choices[0].finish_reason == "length":
                        truncated = True
            clean, thinking = strip_thinking(full_response)
            if thinking:
                logger.info(f"模型思考摘要: {thinking}")
            if not silent:
                print(clean)
            return clean, truncated
        else:
            content = response.choices[0].message.content
            truncated = response.choices[0].finish_reason == "length"
            clean, thinking = strip_thinking(content)
            if thinking:
                logger.info(f"模型思考摘要: {thinking}")
            if not silent:
                print(clean)
            return clean, truncated

    def _call_anthropic(self, messages: List[Dict], stream: bool, silent: bool = False) -> Tuple[str, bool]:
        from anthropic import Anthropic
        client = Anthropic(api_key=self.provider_config["api_key"])

        system_msg = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg += msg["content"] + "\n"
            else:
                user_messages.append(msg)

        response = client.messages.create(
            model=self.provider_config["default_model"],
            system=system_msg if system_msg else None,
            messages=user_messages,
            max_tokens=self.config.get("max_tokens", 16384),
            temperature=self.config.get("temperature", 0.7),
            stream=stream
        )
        if stream:
            full_response = ""
            truncated = False
            for chunk in response:
                if chunk.type == "content_block_delta":
                    full_response += chunk.delta.text
                elif chunk.type == "message_delta":
                    if hasattr(chunk, 'delta') and hasattr(chunk.delta, 'stop_reason'):
                        if chunk.delta.stop_reason == "max_tokens":
                            truncated = True
            clean, thinking = strip_thinking(full_response)
            if thinking:
                logger.info(f"模型思考摘要: {thinking}")
            if not silent:
                print(clean)
            return clean, truncated
        else:
            content = response.content[0].text
            truncated = response.stop_reason == "max_tokens"
            clean, thinking = strip_thinking(content)
            if thinking:
                logger.info(f"模型思考摘要: {thinking}")
            if not silent:
                print(clean)
            return clean, truncated

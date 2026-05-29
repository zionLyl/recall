"""OpenAI / OpenAI-compatible adapter (also serves DeepSeek, Qwen, etc.)."""

from __future__ import annotations

import os

from .base import Adapter, ChatResult


class OpenAIAdapter(Adapter):
    provider = "openai"

    def chat(self, prompt: str, system: str | None = None) -> ChatResult:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run: pip install 'recall-ai[openai]'"
            ) from e

        api_key = self.api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get(
            "RECALL_API_KEY"
        )
        client = OpenAI(api_key=api_key, base_url=self.base_url)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = client.chat.completions.create(model=self.model, messages=messages)
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return ChatResult(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=self.model,
            provider=self.provider,
        )

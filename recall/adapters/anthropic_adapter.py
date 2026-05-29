"""Anthropic (Claude) adapter."""

from __future__ import annotations

import os

from .base import Adapter, ChatResult


class AnthropicAdapter(Adapter):
    provider = "anthropic"

    def chat(self, prompt: str, system: str | None = None) -> ChatResult:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install 'recall-ai[anthropic]'"
            ) from e

        api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
            "RECALL_API_KEY"
        )
        client = anthropic.Anthropic(api_key=api_key, base_url=self.base_url)

        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        resp = client.messages.create(**kwargs)
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        return ChatResult(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=self.model,
            provider=self.provider,
        )

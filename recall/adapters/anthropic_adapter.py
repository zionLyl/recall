"""Anthropic (Claude) adapter."""

from __future__ import annotations

import os
from typing import Iterator

from .base import Adapter, ChatResult, approx_tokens


class AnthropicAdapter(Adapter):
    provider = "anthropic"

    def _client(self):
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install 'zion-recall-ai[anthropic]'"
            ) from e
        api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
            "RECALL_API_KEY"
        )
        return anthropic.Anthropic(api_key=api_key, base_url=self.base_url)

    def _kwargs(self, prompt: str, system: str | None,
                history: list[dict] | None = None) -> dict:
        messages = [
            {"role": t["role"], "content": t["content"]} for t in (history or [])
        ]
        messages.append({"role": "user", "content": prompt})
        kwargs = {"model": self.model, "max_tokens": 1024, "messages": messages}
        if system:
            kwargs["system"] = system
        return kwargs

    def chat(self, prompt: str, system: str | None = None,
             history: list[dict] | None = None) -> ChatResult:
        client = self._client()
        resp = client.messages.create(**self._kwargs(prompt, system, history))
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

    def stream(self, prompt: str, system: str | None = None,
               history: list[dict] | None = None) -> Iterator[str]:
        client = self._client()
        parts: list[str] = []
        in_tok = out_tok = 0
        with client.messages.stream(**self._kwargs(prompt, system, history)) as stream:
            for chunk in stream.text_stream:
                parts.append(chunk)
                yield chunk
            final = stream.get_final_message()
            usage = getattr(final, "usage", None)
            if usage is not None:
                in_tok = getattr(usage, "input_tokens", 0) or 0
                out_tok = getattr(usage, "output_tokens", 0) or 0

        text = "".join(parts)
        if not in_tok:
            in_tok = approx_tokens((system or "") + prompt)
        if not out_tok:
            out_tok = approx_tokens(text)
        self.last_result = ChatResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            model=self.model, provider=self.provider,
        )

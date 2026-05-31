"""OpenAI / OpenAI-compatible adapter (also serves DeepSeek, Qwen, etc.)."""

from __future__ import annotations

import os
from typing import Iterator

from .base import Adapter, ChatResult, approx_tokens


class OpenAIAdapter(Adapter):
    provider = "openai"

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run: pip install 'zion-recall-ai[openai]'"
            ) from e
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get(
            "RECALL_API_KEY"
        )
        return OpenAI(api_key=api_key, base_url=self.base_url)

    def _messages(self, prompt: str, system: str | None, history: list[dict] | None = None):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        for turn in history or []:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": prompt})
        return messages

    def chat(self, prompt: str, system: str | None = None,
             history: list[dict] | None = None) -> ChatResult:
        client = self._client()
        resp = client.chat.completions.create(
            model=self.model, messages=self._messages(prompt, system, history)
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return ChatResult(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=self.model,
            provider=self.provider,
        )

    def stream(self, prompt: str, system: str | None = None,
               history: list[dict] | None = None) -> Iterator[str]:
        client = self._client()
        messages = self._messages(prompt, system, history)

        # Ask for usage in the final chunk; not all OpenAI-compatible servers
        # support stream_options, so fall back gracefully if rejected.
        try:
            resp = client.chat.completions.create(
                model=self.model, messages=messages, stream=True,
                stream_options={"include_usage": True},
            )
        except Exception:  # noqa: BLE001 — older / partial OpenAI-compatible servers
            resp = client.chat.completions.create(
                model=self.model, messages=messages, stream=True,
            )

        parts: list[str] = []
        in_tok = out_tok = 0
        for chunk in resp:
            choices = getattr(chunk, "choices", None)
            if choices:
                delta = getattr(choices[0].delta, "content", None)
                if delta:
                    parts.append(delta)
                    yield delta
            usage = getattr(chunk, "usage", None)
            if usage:
                in_tok = getattr(usage, "prompt_tokens", 0) or in_tok
                out_tok = getattr(usage, "completion_tokens", 0) or out_tok

        text = "".join(parts)
        if not in_tok:
            in_tok = approx_tokens((system or "") + prompt)
        if not out_tok:
            out_tok = approx_tokens(text)
        self.last_result = ChatResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            model=self.model, provider=self.provider,
        )

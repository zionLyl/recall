"""Google Gemini adapter (via the google-generativeai SDK)."""

from __future__ import annotations

import os
from typing import Iterator

from .base import Adapter, ChatResult, approx_tokens


class GeminiAdapter(Adapter):
    provider = "gemini"

    def _model(self, system: str | None):
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise RuntimeError(
                "google-generativeai not installed. Run: pip install 'memstash[gemini]'"
            ) from e
        api_key = self.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get(
            "GOOGLE_API_KEY"
        ) or os.environ.get("MEMSTASH_API_KEY")
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model_name=self.model, system_instruction=system or None)

    @staticmethod
    def _contents(prompt: str, history: list[dict] | None):
        out = []
        for turn in history or []:
            role = "model" if turn["role"] == "assistant" else "user"
            out.append({"role": role, "parts": [turn["content"]]})
        out.append({"role": "user", "parts": [prompt]})
        return out

    @staticmethod
    def _usage(resp) -> tuple[int, int]:
        usage = getattr(resp, "usage_metadata", None)
        if usage is None:
            return 0, 0
        return (
            getattr(usage, "prompt_token_count", 0) or 0,
            getattr(usage, "candidates_token_count", 0) or 0,
        )

    def chat(self, prompt: str, system: str | None = None,
             history: list[dict] | None = None) -> ChatResult:
        model = self._model(system)
        resp = model.generate_content(self._contents(prompt, history))
        text = resp.text or ""
        in_tok, out_tok = self._usage(resp)
        return ChatResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            model=self.model, provider=self.provider,
        )

    def stream(self, prompt: str, system: str | None = None,
               history: list[dict] | None = None) -> Iterator[str]:
        model = self._model(system)
        resp = model.generate_content(self._contents(prompt, history), stream=True)
        parts: list[str] = []
        for chunk in resp:
            piece = getattr(chunk, "text", "") or ""
            if piece:
                parts.append(piece)
                yield piece

        in_tok, out_tok = self._usage(resp)
        text = "".join(parts)
        if not in_tok:
            in_tok = approx_tokens((system or "") + prompt)
        if not out_tok:
            out_tok = approx_tokens(text)
        self.last_result = ChatResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            model=self.model, provider=self.provider,
        )

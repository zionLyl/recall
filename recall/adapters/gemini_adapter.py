"""Google Gemini adapter (via the google-generativeai SDK)."""

from __future__ import annotations

import os

from .base import Adapter, ChatResult


class GeminiAdapter(Adapter):
    provider = "gemini"

    def chat(self, prompt: str, system: str | None = None) -> ChatResult:
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise RuntimeError(
                "google-generativeai not installed. Run: pip install 'recall-ai[gemini]'"
            ) from e

        api_key = self.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get(
            "GOOGLE_API_KEY"
        ) or os.environ.get("RECALL_API_KEY")
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system or None,
        )
        resp = model.generate_content(prompt)
        text = resp.text or ""

        # Token usage if the SDK provides it.
        in_tok = out_tok = 0
        usage = getattr(resp, "usage_metadata", None)
        if usage is not None:
            in_tok = getattr(usage, "prompt_token_count", 0) or 0
            out_tok = getattr(usage, "candidates_token_count", 0) or 0

        return ChatResult(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model=self.model,
            provider=self.provider,
        )

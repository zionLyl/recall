"""Base adapter interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass
class ChatResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


def approx_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for providers that don't report
    usage on streaming responses."""
    return max(1, len(text or "") // 4)


class Adapter:
    provider: str = "base"

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        # Set by stream() once the generator is exhausted, so callers can read
        # final token usage after consuming the chunks.
        self.last_result: Optional[ChatResult] = None

    def chat(self, prompt: str, system: str | None = None) -> ChatResult:
        raise NotImplementedError

    def stream(self, prompt: str, system: str | None = None) -> Iterator[str]:
        """Yield text chunks as they arrive.

        After the generator is fully consumed, ``self.last_result`` holds a
        ``ChatResult`` with the final token counts.

        The default implementation simply wraps the blocking ``chat()`` call and
        yields the whole reply as one chunk, so every adapter supports streaming
        even if its backend doesn't — native adapters override this for true
        token-by-token output.
        """
        result = self.chat(prompt, system=system)
        self.last_result = result
        if result.text:
            yield result.text

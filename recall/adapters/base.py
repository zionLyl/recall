"""Base adapter interface."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


class Adapter:
    provider: str = "base"

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def chat(self, prompt: str, system: str | None = None) -> ChatResult:
        raise NotImplementedError

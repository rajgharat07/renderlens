from __future__ import annotations

import os
from typing import Optional

from renderlens.backends.base import ModelBackend


class GeminiGemmaBackend(ModelBackend):
    """Gemma 4 via Gemini API (open-weight model, hosted)."""

    name = "gemini-gemma4"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemma-4-26b-a4b-it",
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is missing")

    def generate(
        self,
        *,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/png",
        temperature: float = 0.0,
    ) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        parts: list = []
        if image_bytes:
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
        parts.append(types.Part.from_text(text=prompt))

        # Gemma 4 on Gemini API: keep config minimal; structured output
        # support varies — we parse JSON ourselves with repair.
        config = types.GenerateContentConfig(temperature=temperature)
        content = types.Content(role="user", parts=parts)
        resp = client.models.generate_content(
            model=self.model,
            contents=content,
            config=config,
        )
        return (resp.text or "").strip()

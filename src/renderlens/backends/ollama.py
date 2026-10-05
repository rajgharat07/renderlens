"""Optional local backend. Uses Gemma *3* via Ollama — not Gemma 4."""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Optional

from renderlens.backends.base import ModelBackend


class OllamaGemma3Backend(ModelBackend):
    name = "ollama-gemma3"

    def __init__(
        self,
        host: Optional[str] = None,
        model: str = "gemma3:4b",
    ):
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip(
            "/"
        )
        self.model = model or os.environ.get("OLLAMA_MODEL", "gemma3:4b")

    def generate(
        self,
        *,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/png",
        temperature: float = 0.0,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if image_bytes:
            payload["images"] = [base64.b64encode(image_bytes).decode("ascii")]

        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("response") or "").strip()

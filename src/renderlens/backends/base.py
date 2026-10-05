from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class ModelBackend(ABC):
    name: str = "base"

    @abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/png",
        temperature: float = 0.0,
    ) -> str:
        """Return raw text (hopefully JSON). Never print secrets."""
        raise NotImplementedError

"""Parse model JSON with light repair — Gemma may wrap fences or chatter."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from renderlens.schema import ModelTurn


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    # first {...} block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    blob = cleaned[start : end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # trailing commas
        blob2 = re.sub(r",\s*}", "}", blob)
        blob2 = re.sub(r",\s*]", "]", blob2)
        try:
            return json.loads(blob2)
        except json.JSONDecodeError:
            return None


def parse_model_turn(text: str) -> ModelTurn:
    data = extract_json_object(text)
    if not data:
        return ModelTurn(notes="parse_failed", findings=[])
    try:
        return ModelTurn.model_validate(data)
    except Exception:
        # best-effort: keep raw notes
        return ModelTurn(notes=f"validate_failed: {text[:200]}", findings=[])

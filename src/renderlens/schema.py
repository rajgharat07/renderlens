from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Tier(str, Enum):
    VERIFIED = "verified"
    MODEL_OBSERVED = "model_observed"
    DROPPED = "dropped"


class Severity(str, Enum):
    CRITICAL = "critical"
    SERIOUS = "serious"
    MODERATE = "moderate"
    MINOR = "minor"


class BBox(BaseModel):
    """Normalized 0-1 box, or absolute pixels if coords_mode=absolute."""

    x: float
    y: float
    w: float
    h: float
    coords_mode: Literal["normalized", "absolute"] = "normalized"

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        if self.coords_mode == "absolute":
            x1, y1 = int(self.x), int(self.y)
            x2, y2 = int(self.x + self.w), int(self.y + self.h)
        else:
            x1 = int(self.x * width)
            y1 = int(self.y * height)
            x2 = int((self.x + self.w) * width)
            y2 = int((self.y + self.h) * height)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)
        if x2 <= x1:
            x2 = min(width, x1 + 1)
        if y2 <= y1:
            y2 = min(height, y1 + 1)
        return x1, y1, x2, y2


class RequestCrop(BaseModel):
    reason: str = ""
    bbox: BBox


class ProposedFinding(BaseModel):
    id: str
    category: Literal[
        "contrast",
        "text_over_image",
        "truncation",
        "hierarchy",
        "color_only",
        "tap_target",
        "other",
    ]
    severity: Severity = Severity.SERIOUS
    description: str
    bbox: Optional[BBox] = None
    # model-claimed colors; engine re-samples pixels and may disagree
    fg_hex: Optional[str] = None
    bg_hex: Optional[str] = None
    evidence: str = ""


class ModelTurn(BaseModel):
    findings: list[ProposedFinding] = Field(default_factory=list)
    request_crop: Optional[RequestCrop] = None
    notes: str = ""


class Finding(BaseModel):
    id: str
    category: str
    severity: Severity
    tier: Tier
    description: str
    bbox: Optional[BBox] = None
    contrast_ratio: Optional[float] = None
    fg_hex: Optional[str] = None
    bg_hex: Optional[str] = None
    wcag_aa_pass: Optional[bool] = None
    fix_kind: Optional[Literal["recolor_text", "scrim", "none"]] = None
    fix_detail: str = ""
    drop_reason: str = ""


class AuditReport(BaseModel):
    image_path: str
    model: str
    findings: list[Finding] = Field(default_factory=list)
    verified: list[Finding] = Field(default_factory=list)
    model_observed: list[Finding] = Field(default_factory=list)
    dropped: list[Finding] = Field(default_factory=list)
    latency_ms: float = 0.0
    zoom_rounds: int = 0
    localization_mode: Literal["bbox", "tile_grid"] = "bbox"
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("findings", mode="before")
    @classmethod
    def _ok(cls, v):
        return v or []

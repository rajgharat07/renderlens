"""Core audit pipeline: Gemma proposes → zoom loop → WCAG tiers."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Literal, Optional

from PIL import Image

from renderlens.backends.base import ModelBackend
from renderlens.contrast import passes_aa, sample_region, tile_boxes
from renderlens.parse import extract_json_object, parse_model_turn
from renderlens.prompts import (
    first_pass_prompt,
    second_pass_prompt,
    tile_flag_prompt,
    zoom_followup_prompt,
)
from renderlens.schema import (
    AuditReport,
    BBox,
    Finding,
    ProposedFinding,
    Severity,
    Tier,
)


def _img_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        ext, "image/png"
    )


def verify_finding(
    img: Image.Image,
    prop: ProposedFinding,
    *,
    bg_mode: Literal["solid", "worst", "p5"] = "worst",
) -> Finding:
    w, h = img.size
    bbox = prop.bbox
    if bbox is None:
        return Finding(
            id=prop.id,
            category=prop.category,
            severity=prop.severity,
            tier=Tier.MODEL_OBSERVED,
            description=prop.description,
            fix_kind="none",
            fix_detail="no bbox from model",
        )

    box = bbox.to_pixels(w, h)
    if prop.category in ("contrast", "text_over_image"):
        if prop.category == "text_over_image":
            mode: Literal["solid", "worst", "p5"] = (
                "p5" if bg_mode == "p5" else "worst"
            )
        else:
            mode = bg_mode if bg_mode in ("solid", "worst", "p5") else "worst"
        sampled = sample_region(img, box, bg_mode=mode)
        aa = passes_aa(sampled.ratio)
        if not aa:
            fix_kind = "scrim" if prop.category == "text_over_image" else "recolor_text"
            return Finding(
                id=prop.id,
                category=prop.category,
                severity=prop.severity,
                tier=Tier.VERIFIED,
                description=prop.description,
                bbox=bbox,
                contrast_ratio=round(sampled.ratio, 2),
                fg_hex="#{:02x}{:02x}{:02x}".format(*sampled.fg),
                bg_hex="#{:02x}{:02x}{:02x}".format(*sampled.bg),
                wcag_aa_pass=False,
                fix_kind=fix_kind,  # type: ignore[arg-type]
                fix_detail=f"measured {sampled.ratio:.2f}:1 (mode={sampled.bg_mode})",
            )
        return Finding(
            id=prop.id,
            category=prop.category,
            severity=prop.severity,
            tier=Tier.DROPPED,
            description=prop.description,
            bbox=bbox,
            contrast_ratio=round(sampled.ratio, 2),
            fg_hex="#{:02x}{:02x}{:02x}".format(*sampled.fg),
            bg_hex="#{:02x}{:02x}{:02x}".format(*sampled.bg),
            wcag_aa_pass=True,
            drop_reason=f"math AA pass ({sampled.ratio:.2f}:1)",
        )

    return Finding(
        id=prop.id,
        category=prop.category,
        severity=prop.severity,
        tier=Tier.MODEL_OBSERVED,
        description=prop.description,
        bbox=bbox,
        fix_kind="none",
        fix_detail=prop.evidence or "",
    )


def run_audit(
    image_path: Path,
    backend: ModelBackend,
    *,
    temperature: float = 0.0,
    max_zoom_rounds: int = 2,
    use_second_pass: bool = True,
    localization_mode: Literal["bbox", "tile_grid"] = "bbox",
    bg_mode: Literal["solid", "worst", "p5"] = "worst",
    raw_dump_dir: Optional[Path] = None,
) -> AuditReport:
    t0 = time.perf_counter()
    path = Path(image_path)
    img = Image.open(path).convert("RGB")
    mime = _mime(path)
    zoom_rounds = 0
    raw_log: list[str] = []

    if localization_mode == "tile_grid":
        raw = backend.generate(
            prompt=tile_flag_prompt(4, 4),
            image_bytes=_img_bytes(img),
            mime_type=mime,
            temperature=temperature,
        )
        raw_log.append(raw)
        data = extract_json_object(raw) or {}
        bad = set(data.get("bad_tiles") or [])
        tiles = tile_boxes(*img.size, 4, 4)
        turn_findings: list[ProposedFinding] = []
        for i, box in enumerate(tiles):
            if i not in bad:
                continue
            x1, y1, x2, y2 = box
            turn_findings.append(
                ProposedFinding(
                    id=f"tile-{i}",
                    category="contrast",
                    severity=Severity.SERIOUS,
                    description=f"Model flagged tile {i}",
                    bbox=BBox(
                        x=x1 / img.size[0],
                        y=y1 / img.size[1],
                        w=(x2 - x1) / img.size[0],
                        h=(y2 - y1) / img.size[1],
                    ),
                )
            )
    else:
        raw = backend.generate(
            prompt=first_pass_prompt(),
            image_bytes=_img_bytes(img),
            mime_type=mime,
            temperature=temperature,
        )
        raw_log.append(raw)
        turn = parse_model_turn(raw)

        while turn.request_crop and zoom_rounds < max_zoom_rounds:
            zoom_rounds += 1
            bb = turn.request_crop.bbox
            box = bb.to_pixels(*img.size)
            crop = img.crop(box)
            cw, ch = crop.size
            crop = crop.resize((max(1, cw * 2), max(1, ch * 2)), Image.Resampling.BICUBIC)
            raw2 = backend.generate(
                prompt=zoom_followup_prompt(turn.model_dump_json()),
                image_bytes=_img_bytes(crop),
                mime_type="image/png",
                temperature=temperature,
            )
            raw_log.append(raw2)
            zoom_turn = parse_model_turn(raw2)
            merged = list(turn.findings)
            fw, fh = img.size
            x1, y1, x2, y2 = box
            for f in zoom_turn.findings:
                if f.bbox and f.bbox.coords_mode == "normalized":
                    abs_x = x1 + f.bbox.x * (x2 - x1)
                    abs_y = y1 + f.bbox.y * (y2 - y1)
                    abs_w = f.bbox.w * (x2 - x1)
                    abs_h = f.bbox.h * (y2 - y1)
                    f.bbox = BBox(
                        x=abs_x / fw,
                        y=abs_y / fh,
                        w=abs_w / fw,
                        h=abs_h / fh,
                    )
                merged.append(f)
            turn.findings = merged
            turn.request_crop = zoom_turn.request_crop

        if use_second_pass and turn.findings:
            raw3 = backend.generate(
                prompt=second_pass_prompt(turn.model_dump_json()),
                image_bytes=_img_bytes(img),
                mime_type=mime,
                temperature=temperature,
            )
            raw_log.append(raw3)
            second = parse_model_turn(raw3)
            if second.findings:
                keep_ids = {f.id for f in second.findings}
                turn.findings = [
                    f for f in turn.findings if f.id in keep_ids
                ] or second.findings

        turn_findings = turn.findings

    verified: list[Finding] = []
    observed: list[Finding] = []
    dropped: list[Finding] = []
    for prop in turn_findings:
        f = verify_finding(img, prop, bg_mode=bg_mode)
        if f.tier == Tier.VERIFIED:
            verified.append(f)
        elif f.tier == Tier.DROPPED:
            dropped.append(f)
        else:
            observed.append(f)

    if raw_dump_dir:
        dump = Path(raw_dump_dir)
        dump.mkdir(parents=True, exist_ok=True)
        for i, blob in enumerate(raw_log):
            (dump / f"{path.stem}_turn{i}.txt").write_text(blob, encoding="utf-8")

    return AuditReport(
        image_path=str(path),
        model=getattr(backend, "model", backend.name),
        findings=verified + observed + dropped,
        verified=verified,
        model_observed=observed,
        dropped=dropped,
        latency_ms=(time.perf_counter() - t0) * 1000,
        zoom_rounds=zoom_rounds,
        localization_mode=localization_mode,
        meta={"backend": backend.name, "bg_mode": bg_mode},
    )

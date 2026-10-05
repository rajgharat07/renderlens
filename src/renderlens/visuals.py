"""Annotated screenshot + auto-fix preview rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageDraw, ImageFont

from renderlens.contrast import (
    nearest_aa_text_color,
    rgb_to_hex,
    sample_region,
    scrim_alpha_for_aa,
)
from renderlens.schema import Finding, Tier


_TIER_COLOR = {
    Tier.VERIFIED: (220, 50, 50),
    Tier.MODEL_OBSERVED: (230, 160, 20),
    Tier.DROPPED: (120, 120, 120),
}


def _font(size: int = 14):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def annotate_image(img: Image.Image, findings: Iterable[Finding]) -> Image.Image:
    out = img.convert("RGBA").copy()
    draw = ImageDraw.Draw(out)
    font = _font(14)
    w, h = out.size
    for f in findings:
        if f.tier == Tier.DROPPED or not f.bbox:
            continue
        x1, y1, x2, y2 = f.bbox.to_pixels(w, h)
        color = _TIER_COLOR.get(f.tier, (200, 200, 200))
        draw.rectangle([x1, y1, x2, y2], outline=color + (255,), width=3)
        label = f.tier.value
        if f.contrast_ratio is not None:
            label = f"{f.contrast_ratio:.2f}:1 [{f.tier.value}]"
        # label background
        tw, th = draw.textbbox((0, 0), label, font=font)[2:]
        ly = max(0, y1 - th - 4)
        draw.rectangle([x1, ly, x1 + tw + 6, ly + th + 4], fill=color + (230,))
        draw.text((x1 + 3, ly + 2), label, fill=(255, 255, 255), font=font)
    return out.convert("RGB")


def auto_fix_preview(
    img: Image.Image,
    finding: Finding,
    *,
    bg_mode: str = "worst",
) -> tuple[Image.Image, str]:
    """Return (fixed_image_crop_or_full, description).

    Solid-ish bg -> recolor hypothetical overlay note.
    Image/gradient -> draw semi-transparent scrim behind the text box.
    """
    if not finding.bbox:
        return img.copy(), "no bbox; cannot auto-fix"
    w, h = img.size
    box = finding.bbox.to_pixels(w, h)
    mode = "worst" if bg_mode in ("worst", "p5") else "solid"
    if bg_mode == "p5":
        mode = "p5"
    sampled = sample_region(img, box, bg_mode=mode)  # type: ignore[arg-type]

    # treat as image/gradient when variance is high
    x1, y1, x2, y2 = box
    crop = img.convert("RGB").crop((x1, y1, x2, y2))
    pix = list(crop.getdata())
    if len(pix) > 1:
        mean = tuple(sum(p[i] for p in pix) / len(pix) for i in range(3))
        var = sum(sum((p[i] - mean[i]) ** 2 for i in range(3)) for p in pix) / len(pix)
    else:
        var = 0.0

    fixed = img.convert("RGBA").copy()
    if var > 800:  # busy background -> scrim
        alpha = scrim_alpha_for_aa(sampled.fg, sampled.bg)
        overlay = Image.new("RGBA", (x2 - x1, y2 - y1), (0, 0, 0, int(255 * alpha)))
        fixed.alpha_composite(overlay, (x1, y1))
        detail = (
            f"scrim alpha={alpha:.2f} over image/gradient "
            f"(bg sample {rgb_to_hex(sampled.bg)}, was {sampled.ratio:.2f}:1)"
        )
        return fixed.convert("RGB"), detail

    new_fg = nearest_aa_text_color(sampled.fg, sampled.bg)
    # we can't re-typeset unknown fonts; draw a solid bar in the fixed fg as a preview chip
    draw = ImageDraw.Draw(fixed)
    draw.rectangle([x1, y1, x2, y2], outline=(0, 200, 80, 255), width=3)
    chip = Image.new("RGB", (max(40, x2 - x1), 18), new_fg)
    fixed.paste(chip, (x1, max(0, y1 - 22)))
    detail = (
        f"suggested text color {rgb_to_hex(new_fg)} on solid-ish bg "
        f"{rgb_to_hex(sampled.bg)} (was {sampled.ratio:.2f}:1)"
    )
    return fixed.convert("RGB"), detail


def save_image(img: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path

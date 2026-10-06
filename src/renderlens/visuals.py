"""Annotated screenshot + auto-fix preview rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Literal

from PIL import Image, ImageDraw, ImageFont

from renderlens.contrast import (
    contrast_ratio,
    nearest_aa_text_color,
    passes_aa,
    relative_luminance,
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
        tw, th = draw.textbbox((0, 0), label, font=font)[2:]
        ly = max(0, y1 - th - 4)
        draw.rectangle([x1, ly, x1 + tw + 6, ly + th + 4], fill=color + (230,))
        draw.text((x1 + 3, ly + 2), label, fill=(255, 255, 255), font=font)
    return out.convert("RGB")


def _region_variance(pix: list[tuple[int, int, int]]) -> float:
    if len(pix) <= 1:
        return 0.0
    mean = tuple(sum(p[i] for p in pix) / len(pix) for i in range(3))
    return sum(sum((p[i] - mean[i]) ** 2 for i in range(3)) for p in pix) / len(pix)


def _should_use_scrim(
    finding: Finding,
    sampled_fg: tuple[int, int, int],
    sampled_bg: tuple[int, int, int],
    variance: float,
) -> bool:
    if finding.category == "text_over_image":
        return True
    if finding.fix_kind == "scrim":
        return True
    # smooth sky/gradient under light text still needs a scrim, even if variance is low
    if relative_luminance(sampled_fg) >= 0.55 and relative_luminance(sampled_bg) >= 0.45:
        return True
    if variance > 400:
        return True
    return False


def _apply_scrim_behind_text(
    img: Image.Image,
    box: tuple[int, int, int, int],
    *,
    alpha: float,
    pad: int = 10,
) -> Image.Image:
    """Darken background pixels in/near the box; keep bright text pixels readable.

    We don't have a real z-order layer, so treat bright pixels as text and blend
    the scrim into everything else — reads as a panel *behind* the letters.
    """
    x1, y1, x2, y2 = box
    w, h = img.size
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w, x2 + pad)
    y2 = min(h, y2 + pad)

    fixed = img.convert("RGB").copy()
    region = fixed.crop((x1, y1, x2, y2))
    pix = list(region.getdata())
    a = max(0.35, min(1.0, alpha))  # visible enough for demos
    out_pix = []
    for r, g, b in pix:
        lum = relative_luminance((r, g, b))
        if lum >= 0.72:
            # keep / boost text
            out_pix.append((255, 255, 255))
        else:
            # scrim into background
            out_pix.append(
                (
                    int(r * (1 - a)),
                    int(g * (1 - a)),
                    int(b * (1 - a)),
                )
            )
    region.putdata(out_pix)
    fixed.paste(region, (x1, y1))

    # soft "fixed" outline so the slide reads clearly
    draw = ImageDraw.Draw(fixed)
    draw.rectangle([x1, y1, x2 - 1, y2 - 1], outline=(34, 197, 94), width=3)
    return fixed


def auto_fix_preview(
    img: Image.Image,
    finding: Finding,
    *,
    bg_mode: str = "worst",
) -> tuple[Image.Image, str]:
    """Return (fixed preview image, short description)."""
    if not finding.bbox:
        return img.copy(), "no bbox; cannot auto-fix"

    w, h = img.size
    box = finding.bbox.to_pixels(w, h)
    mode: Literal["solid", "worst", "p5"]
    if bg_mode == "p5":
        mode = "p5"
    elif bg_mode == "solid":
        mode = "solid"
    else:
        mode = "worst"

    sampled = sample_region(img, box, bg_mode=mode)
    x1, y1, x2, y2 = box
    crop = img.convert("RGB").crop((x1, y1, x2, y2))
    pix = list(crop.getdata())
    variance = _region_variance(pix)

    if _should_use_scrim(finding, sampled.fg, sampled.bg, variance):
        alpha = scrim_alpha_for_aa(sampled.fg, sampled.bg)
        # guarantee AA against the worst bg sample after blend
        blended = tuple(int(sampled.bg[i] * (1 - max(alpha, 0.35))) for i in range(3))
        new_ratio = contrast_ratio((255, 255, 255), blended)
        # bump alpha if still short
        a = max(alpha, 0.35)
        while a < 1.0 and not passes_aa(new_ratio, large_text=True):
            a += 0.05
            blended = tuple(int(sampled.bg[i] * (1 - a)) for i in range(3))
            new_ratio = contrast_ratio((255, 255, 255), blended)

        fixed = _apply_scrim_behind_text(img, box, alpha=a)
        detail = (
            f"scrim behind text (alpha={a:.2f}); "
            f"approx {new_ratio:.2f}:1 after fix (was {sampled.ratio:.2f}:1)"
        )
        return fixed, detail

    # solid-ish: suggest a readable text color chip + outline
    new_fg = nearest_aa_text_color(sampled.fg, sampled.bg)
    fixed = img.convert("RGBA").copy()
    draw = ImageDraw.Draw(fixed)
    draw.rectangle([x1, y1, x2, y2], outline=(34, 197, 94, 255), width=3)
    chip_h = 18
    chip = Image.new("RGB", (max(40, x2 - x1), chip_h), new_fg)
    fixed.paste(chip, (x1, max(0, y1 - chip_h - 4)))
    detail = (
        f"suggested text color {rgb_to_hex(new_fg)} on solid-ish bg "
        f"{rgb_to_hex(sampled.bg)} (was {sampled.ratio:.2f}:1)"
    )
    return fixed.convert("RGB"), detail


def auto_fix_all(
    img: Image.Image,
    findings: Iterable[Finding],
    *,
    bg_mode: str = "worst",
) -> tuple[Image.Image, str]:
    """Apply auto-fix for every verified contrast-like finding (demo-friendly)."""
    targets = [
        f
        for f in findings
        if f.tier == Tier.VERIFIED
        and f.bbox
        and f.category in ("text_over_image", "contrast")
    ]
    if not targets:
        return img.copy(), "no verified contrast findings"

    out = img.convert("RGB")
    details: list[str] = []
    for f in targets:
        out, detail = auto_fix_preview(out, f, bg_mode=bg_mode)
        details.append(f"{f.id}: {detail}")
    return out, "; ".join(details)


def save_image(img: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path

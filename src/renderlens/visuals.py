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


def _is_light_text_pixel(r: int, g: int, b: int) -> bool:
    """Near-pure white glyphs. Rejects cool/cyan sky even when very bright."""
    # Demo sky hits (245,255,255) etc.; real white type is ~ (255,255,255).
    if b > r + 4:  # cyan/blue cast => sky, not type
        return False
    if min(r, g, b) < 250:
        return False
    return (max(r, g, b) - min(r, g, b)) <= 6


def _expand_box_to_glyphs(
    img: Image.Image,
    box: tuple[int, int, int, int],
    *,
    margin: int = 40,
) -> tuple[int, int, int, int]:
    """Grow a bbox so clipped letterforms just outside still sit in the scrim."""
    x1, y1, x2, y2 = box
    w, h = img.size
    sx1 = max(0, x1 - margin)
    sy1 = max(0, y1 - margin)
    sx2 = min(w, x2 + margin)
    sy2 = min(h, y2 + margin)
    crop = img.convert("RGB").crop((sx1, sy1, sx2, sy2))
    cw, ch = crop.size
    pix = list(crop.getdata())

    # per-row glyph counts — skip full-bleed bright bands (false sky hits)
    row_hits = [0] * ch
    xs: list[int] = []
    ys: list[int] = []
    for i, (r, g, b) in enumerate(pix):
        if not _is_light_text_pixel(r, g, b):
            continue
        x = i % cw
        y = i // cw
        row_hits[y] += 1
        xs.append(x)
        ys.append(y)
    if not xs:
        return box

    max_row = max(8, int(cw * 0.45))  # text rows are sparse; sky bands are dense
    keep = {y for y, n in enumerate(row_hits) if 3 <= n <= max_row}
    if not keep:
        return box
    xs = [x for x, y in zip(xs, ys) if y in keep]
    ys = [y for y in ys if y in keep]
    if not xs:
        return box
    return (
        min(x1, sx1 + min(xs)),
        min(y1, sy1 + min(ys)),
        max(x2, sx1 + max(xs) + 1),
        max(y2, sy1 + max(ys) + 1),
    )


def _apply_scrim_behind_text(
    img: Image.Image,
    box: tuple[int, int, int, int],
    *,
    alpha: float,
    pad: int = 12,
) -> Image.Image:
    """Paint a dark panel in the box, then put light text pixels back on top."""
    x1, y1, x2, y2 = box
    w, h = img.size
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w, x2 + pad)
    y2 = min(h, y2 + pad)

    fixed = img.convert("RGB").copy()
    region = fixed.crop((x1, y1, x2, y2))
    pix = list(region.getdata())
    a = max(0.45, min(0.85, alpha))

    # remember glyph pixels before we darken the panel
    text_mask = [_is_light_text_pixel(r, g, b) for r, g, b in pix]

    out_pix = []
    for (r, g, b), is_text in zip(pix, text_mask):
        if is_text:
            out_pix.append((255, 255, 255))
        else:
            out_pix.append((int(r * (1 - a)), int(g * (1 - a)), int(b * (1 - a))))
    region.putdata(out_pix)
    fixed.paste(region, (x1, y1))

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

        box = _expand_box_to_glyphs(img, box)
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
    """Apply auto-fix for verified contrast-like findings.

    When several light-on-image findings sit close together (typical hero),
    use one union scrim panel so the before/after reads cleanly on slides.
    """
    targets = [
        f
        for f in findings
        if f.tier == Tier.VERIFIED
        and f.bbox
        and f.category in ("text_over_image", "contrast")
    ]
    if not targets:
        return img.copy(), "no verified contrast findings"

    w, h = img.size
    mode: Literal["solid", "worst", "p5"] = (
        "p5" if bg_mode == "p5" else "solid" if bg_mode == "solid" else "worst"
    )

    # decide if the group should share one scrim
    boxes = [f.bbox.to_pixels(w, h) for f in targets if f.bbox]
    samples = [sample_region(img, b, bg_mode=mode) for b in boxes]
    use_group_scrim = any(
        _should_use_scrim(f, s.fg, s.bg, 0.0) for f, s in zip(targets, samples)
    )

    if use_group_scrim and len(boxes) >= 1:
        ux1 = min(b[0] for b in boxes)
        uy1 = min(b[1] for b in boxes)
        ux2 = max(b[2] for b in boxes)
        uy2 = max(b[3] for b in boxes)
        # pull in letterforms Gemma's box clipped; pad reads cleaner on slides
        ux1, uy1, ux2, uy2 = _expand_box_to_glyphs(img, (ux1, uy1, ux2, uy2))
        uy1 = max(0, uy1 - 12)  # display-type headroom above the first line
        uy2 = min(h, uy2 + 8)
        worst_bg = min(samples, key=lambda s: s.ratio).bg
        fg = (255, 255, 255)
        # target normal AA (4.5:1) so the panel reads clearly in the deck
        alpha = scrim_alpha_for_aa(fg, worst_bg, large_text=False)
        a = max(alpha, 0.55)
        blended = tuple(int(worst_bg[i] * (1 - a)) for i in range(3))
        new_ratio = contrast_ratio(fg, blended)
        while a < 0.85 and not passes_aa(new_ratio, large_text=False):
            a += 0.05
            blended = tuple(int(worst_bg[i] * (1 - a)) for i in range(3))
            new_ratio = contrast_ratio(fg, blended)
        fixed = _apply_scrim_behind_text(img, (ux1, uy1, ux2, uy2), alpha=a, pad=28)
        detail = (
            f"hero scrim over {len(targets)} regions (alpha={a:.2f}); "
            f"approx {new_ratio:.2f}:1 after fix"
        )
        return fixed, detail

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

"""WCAG contrast math + pixel sampling. Pure functions, no model calls."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Literal, Optional

from PIL import Image


def _srgb_to_linear(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def passes_aa(ratio: float, *, large_text: bool = False) -> bool:
    return ratio >= (3.0 if large_text else 4.5)


def passes_aaa(ratio: float, *, large_text: bool = False) -> bool:
    return ratio >= (4.5 if large_text else 7.0)


@dataclass
class SampledColors:
    fg: tuple[int, int, int]
    bg: tuple[int, int, int]
    ratio: float
    bg_mode: str  # solid | worst | p5


def _median_rgb(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not pixels:
        return (128, 128, 128)
    rs = sorted(p[0] for p in pixels)
    gs = sorted(p[1] for p in pixels)
    bs = sorted(p[2] for p in pixels)
    mid = len(pixels) // 2
    return (rs[mid], gs[mid], bs[mid])


def sample_region(
    img: Image.Image,
    box: tuple[int, int, int, int],
    *,
    bg_mode: Literal["solid", "worst", "p5"] = "worst",
) -> SampledColors:
    """Estimate fg/bg inside a box.

    Heuristic: darkest/lightest clusters via luminance — works for typical UI
    text (dark on light or light on dark). For image backgrounds use worst/p5.
    """
    x1, y1, x2, y2 = box
    crop = img.convert("RGB").crop((x1, y1, x2, y2))
    pixels = list(crop.getdata())
    if not pixels:
        mid = (128, 128, 128)
        return SampledColors(mid, mid, 1.0, bg_mode)

    # split by luminance to guess text vs background
    scored = [(relative_luminance(p), p) for p in pixels]
    scored.sort(key=lambda t: t[0])
    n = len(scored)
    dark = [p for _, p in scored[: max(1, n // 5)]]
    light = [p for _, p in scored[-(max(1, n // 5)) :]]
    dark_m = _median_rgb(dark)
    light_m = _median_rgb(light)

    # majority of area is usually background
    median_all = _median_rgb(pixels)
    if abs(relative_luminance(median_all) - relative_luminance(dark_m)) < abs(
        relative_luminance(median_all) - relative_luminance(light_m)
    ):
        bg_guess, fg_guess = dark_m, light_m
    else:
        bg_guess, fg_guess = light_m, dark_m

    if bg_mode == "solid":
        bg = bg_guess
    else:
        # luminance of every pixel as candidate background under text
        lums = [relative_luminance(p) for p in pixels]
        if bg_mode == "p5":
            # 5th percentile toward the side that hurts contrast vs fg
            target = sorted(lums)[max(0, int(0.05 * (n - 1)))]
        else:  # worst: pick bg luminance that minimizes contrast vs fg
            fg_l = relative_luminance(fg_guess)
            # worst bg is the one closest in luminance to fg
            target = min(lums, key=lambda L: abs(L - fg_l))
        # pick a real pixel near that luminance
        bg = min(pixels, key=lambda p: abs(relative_luminance(p) - target))

    ratio = contrast_ratio(fg_guess, bg)
    return SampledColors(fg_guess, bg, ratio, bg_mode)


def nearest_aa_text_color(
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
    *,
    large_text: bool = False,
) -> tuple[int, int, int]:
    """Keep hue; darken/lighten until AA passes (or hit black/white)."""
    r, g, b = [c / 255.0 for c in fg]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    bg_l = relative_luminance(bg)
    # decide direction: move away from background luminance
    step = 0.02
    direction = -1 if bg_l > 0.5 else 1
    best = fg
    for _ in range(60):
        if passes_aa(contrast_ratio(best, bg), large_text=large_text):
            return best
        v = min(1.0, max(0.0, v + direction * step))
        rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
        best = (int(rr * 255), int(gg * 255), int(bb * 255))
    # last resort hard black/white
    for candidate in ((0, 0, 0), (255, 255, 255)):
        if passes_aa(contrast_ratio(candidate, bg), large_text=large_text):
            return candidate
    return best


def scrim_alpha_for_aa(
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
    *,
    scrim_rgb: tuple[int, int, int] = (0, 0, 0),
    large_text: bool = False,
) -> float:
    """Smallest alpha in [0,1] so blended scrim+bg vs fg passes AA."""
    for i in range(0, 101):
        a = i / 100.0
        blended = tuple(
            int(scrim_rgb[c] * a + bg[c] * (1 - a)) for c in range(3)
        )
        if passes_aa(contrast_ratio(fg, blended), large_text=large_text):
            return a
    return 1.0


def tile_boxes(
    width: int, height: int, cols: int = 4, rows: int = 4
) -> list[tuple[int, int, int, int]]:
    boxes = []
    tw, th = width // cols, height // rows
    for r in range(rows):
        for c in range(cols):
            x1, y1 = c * tw, r * th
            x2 = width if c == cols - 1 else (c + 1) * tw
            y2 = height if r == rows - 1 else (r + 1) * th
            boxes.append((x1, y1, x2, y2))
    return boxes

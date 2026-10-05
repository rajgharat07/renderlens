from renderlens.contrast import (
    contrast_ratio,
    hex_to_rgb,
    nearest_aa_text_color,
    passes_aa,
    relative_luminance,
    sample_region,
    scrim_alpha_for_aa,
)
from PIL import Image, ImageDraw


def test_black_on_white_passes():
    assert passes_aa(contrast_ratio((0, 0, 0), (255, 255, 255)))


def test_white_on_light_sky_fails():
    sky = (200, 220, 255)
    assert not passes_aa(contrast_ratio((255, 255, 255), sky))


def test_nearest_aa_improves():
    bg = hex_to_rgb("#c8dcff")
    fg = (255, 255, 255)
    fixed = nearest_aa_text_color(fg, bg)
    assert passes_aa(contrast_ratio(fixed, bg))


def test_scrim_helps_white_on_busy():
    fg = (255, 255, 255)
    bg = (210, 230, 255)
    a = scrim_alpha_for_aa(fg, bg)
    assert 0 < a <= 1
    blended = tuple(int(0 * a + bg[i] * (1 - a)) for i in range(3))
    assert passes_aa(contrast_ratio(fg, blended))


def test_sample_region_worst_mode():
    img = Image.new("RGB", (100, 40), (220, 230, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 5, 90, 35], fill=(255, 255, 255))
    sampled = sample_region(img, (10, 5, 90, 35), bg_mode="worst")
    assert sampled.ratio >= 1.0
    assert relative_luminance(sampled.fg) >= 0

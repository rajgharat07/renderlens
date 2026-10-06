"""Hero scrim mask must darken tinted sky while keeping pure white type."""

from PIL import Image, ImageDraw

from renderlens.schema import BBox, Finding, Severity, Tier
from renderlens.visuals import _is_light_text_pixel, auto_fix_all


def test_light_text_mask_rejects_cyan_sky():
    assert _is_light_text_pixel(255, 255, 255)
    assert not _is_light_text_pixel(245, 255, 255)
    assert not _is_light_text_pixel(224, 244, 255)
    assert not _is_light_text_pixel(231, 250, 254)


def test_hero_union_scrim_darkens_sky_keeps_glyphs():
    img = Image.new("RGB", (400, 200), (230, 248, 255))
    draw = ImageDraw.Draw(img)
    draw.text((40, 60), "Hello trails", fill=(255, 255, 255))
    draw.text((40, 110), "Sub line here", fill=(255, 255, 255))

    findings = [
        Finding(
            id="f1",
            category="contrast",
            severity=Severity.CRITICAL,
            tier=Tier.VERIFIED,
            description="headline",
            bbox=BBox(x=0.08, y=0.25, w=0.55, h=0.18, coords_mode="normalized"),
            contrast_ratio=1.0,
            fix_kind="scrim",
        ),
        Finding(
            id="f2",
            category="text_over_image",
            severity=Severity.CRITICAL,
            tier=Tier.VERIFIED,
            description="sub",
            bbox=BBox(x=0.08, y=0.50, w=0.50, h=0.12, coords_mode="normalized"),
            contrast_ratio=1.0,
            fix_kind="scrim",
        ),
    ]
    fixed, detail = auto_fix_all(img, findings)
    assert "hero scrim" in detail
    # sky sample inside panel should be darkened
    assert sum(fixed.getpixel((80, 50))) < sum((230, 248, 255))
    # a pure-white glyph should remain bright
    whites = sum(1 for p in fixed.getdata() if p == (255, 255, 255))
    assert whites > 20

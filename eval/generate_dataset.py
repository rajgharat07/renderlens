"""Generate synthetic screenshots with known injected a11y defects."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent / "dataset"


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def solid_low_contrast(i: int) -> tuple[Image.Image, dict]:
    img = Image.new("RGB", (640, 360), (240, 240, 240))
    d = ImageDraw.Draw(img)
    # light gray text on light bg — known fail
    d.text((40, 80), f"Solid fail #{i}", fill=(200, 200, 200), font=_font(36))
    label = {
        "id": f"solid_{i:02d}",
        "kind": "synthetic",
        "defects": ["contrast"],
        "notes": "light gray on light gray",
    }
    return img, label


def text_over_sky(i: int) -> tuple[Image.Image, dict]:
    img = Image.new("RGB", (640, 360))
    d = ImageDraw.Draw(img)
    for y in range(360):
        c = 190 + int(40 * (1 - y / 360))
        d.line([(0, y), (640, y)], fill=(c, c + 15, 255))
    d.text((30, 60), f"Sky overlay #{i}", fill=(255, 255, 255), font=_font(40))
    label = {
        "id": f"sky_{i:02d}",
        "kind": "synthetic",
        "defects": ["text_over_image", "contrast"],
        "notes": "white on bright gradient",
    }
    return img, label


def truncation(i: int) -> tuple[Image.Image, dict]:
    img = Image.new("RGB", (640, 360), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 40, 220, 90], outline=(0, 0, 0))
    d.text((28, 52), "This label is cut off mid-senten", fill=(0, 0, 0), font=_font(18))
    label = {
        "id": f"trunc_{i:02d}",
        "kind": "synthetic",
        "defects": ["truncation"],
        "notes": "clipped text in a narrow box",
    }
    return img, label


def weak_hierarchy(i: int) -> tuple[Image.Image, dict]:
    img = Image.new("RGB", (640, 360), (255, 255, 255))
    d = ImageDraw.Draw(img)
    # "heading" same size/weight as body
    d.text((30, 40), f"Section title {i}", fill=(80, 80, 80), font=_font(18))
    d.text((30, 70), "Body copy that looks identical in weight and size.", fill=(80, 80, 80), font=_font(18))
    label = {
        "id": f"hier_{i:02d}",
        "kind": "synthetic",
        "defects": ["hierarchy"],
        "notes": "heading indistinguishable from body",
    }
    return img, label


def color_only(i: int) -> tuple[Image.Image, dict]:
    img = Image.new("RGB", (640, 360), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((30, 40), "Status", fill=(0, 0, 0), font=_font(22))
    d.ellipse([30, 90, 70, 130], fill=(34, 197, 94))
    d.ellipse([90, 90, 130, 130], fill=(239, 68, 68))
    label = {
        "id": f"color_{i:02d}",
        "kind": "synthetic",
        "defects": ["color_only"],
        "notes": "status conveyed only by green/red dots",
    }
    return img, label


def good_contrast(i: int) -> tuple[Image.Image, dict]:
    img = Image.new("RGB", (640, 360), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((40, 80), f"Readable #{i}", fill=(0, 0, 0), font=_font(36))
    label = {
        "id": f"ok_{i:02d}",
        "kind": "synthetic",
        "defects": [],
        "notes": "control — should not flag contrast",
    }
    return img, label


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    makers = []
    for i in range(8):
        makers.append(lambda i=i: solid_low_contrast(i))
    for i in range(8):
        makers.append(lambda i=i: text_over_sky(i))
    for i in range(6):
        makers.append(lambda i=i: truncation(i))
    for i in range(6):
        makers.append(lambda i=i: weak_hierarchy(i))
    for i in range(6):
        makers.append(lambda i=i: color_only(i))
    for i in range(6):
        makers.append(lambda i=i: good_contrast(i))

    index = []
    for fn in makers:
        img, label = fn()
        path = ROOT / f"{label['id']}.png"
        img.save(path)
        label["file"] = path.name
        index.append(label)
        print("wrote", path.name)

    (ROOT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"total={len(index)}")


if __name__ == "__main__":
    main()

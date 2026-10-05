"""Build a rendered demo screenshot with white text over a bright hero image."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    root = Path(__file__).resolve().parent
    hero = Image.open(root / "demo_page" / "hero.jpg").convert("RGB")
    # compose a fake browser chrome + white headline over bright sky
    canvas = Image.new("RGB", (1280, 800), (248, 250, 252))
    canvas.paste(hero.resize((1280, 520)), (0, 64))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, 1280, 64], fill=(255, 255, 255))
    try:
        font_lg = ImageFont.truetype("arial.ttf", 54)
        font_sm = ImageFont.truetype("arial.ttf", 22)
        font_nav = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font_lg = font_sm = font_nav = ImageFont.load_default()
    draw.text((24, 20), "Northwind Trails", fill=(15, 23, 42), font=font_nav)
    # white text over bright sky region — the hook
    draw.text((48, 140), "Find trails under bright skies", fill=(255, 255, 255), font=font_lg)
    draw.text(
        (48, 220),
        "Weekend guides across coastal paths — book in minutes.",
        fill=(255, 255, 255),
        font=font_sm,
    )
    draw.rounded_rectangle([48, 280, 260, 330], radius=20, fill=(34, 197, 94))
    draw.text((70, 292), "Start exploring", fill=(5, 46, 22), font=font_nav)
    # lower content with weak hierarchy / color-only chips
    draw.rectangle([40, 560, 1240, 760], fill=(255, 255, 255))
    draw.text((60, 580), "About us", fill=(100, 116, 139), font=font_sm)
    draw.text((60, 630), "Popular tours  ", fill=(15, 23, 42), font=font_nav)
    draw.ellipse([200, 632, 218, 650], fill=(187, 247, 208))
    draw.ellipse([240, 632, 258, 650], fill=(254, 202, 202))
    out = root / "screenshots" / "demo_hero.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

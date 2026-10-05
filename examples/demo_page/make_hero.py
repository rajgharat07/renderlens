"""Generate a synthetic hero.jpg (bright sky + mountains) for the demo page."""

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    out = Path(__file__).resolve().parent / "hero.jpg"
    w, h = 1280, 720
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    # bright sky gradient (makes white text fail)
    for y in range(h // 2):
        t = y / (h // 2)
        c = int(180 + 75 * (1 - t))
        draw.line([(0, y), (w, y)], fill=(c, c + 20, 255))
    for y in range(h // 2, h):
        t = (y - h // 2) / (h // 2)
        g = int(80 + 60 * t)
        draw.line([(0, y), (w, y)], fill=(40, g, 60))
    # simple mountain silhouettes
    draw.polygon([(0, 420), (220, 260), (480, 440), (0, 500)], fill=(70, 90, 110))
    draw.polygon([(300, 500), (640, 220), (980, 500)], fill=(50, 70, 90))
    draw.ellipse([980, 80, 1120, 220], fill=(255, 240, 150))
    img.save(out, quality=92)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

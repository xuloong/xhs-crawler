#!/usr/bin/env python3
"""
Generate app icons for the desktop package.

The generated icon follows the provided Xiaohongshu batch crawler artwork style
and exports PNG, ICNS and ICO variants for PyInstaller.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PNG_PATH = ASSETS / "app_icon.png"
ICNS_PATH = ASSETS / "app_icon.icns"
ICO_PATH = ASSETS / "app_icon.ico"


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    image = draw_icon(1024)
    image.save(PNG_PATH)
    image.save(ICNS_PATH, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
    image.save(ICO_PATH, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"生成图标：{PNG_PATH}")
    print(f"生成图标：{ICNS_PATH}")
    print(f"生成图标：{ICO_PATH}")
    return 0


def draw_icon(size: int) -> Image.Image:
    scale = size / 1024
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)

    shadow = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    rounded = rect(82, 70, 942, 948, scale)
    shadow_draw.rounded_rectangle(offset(rounded, 0, 28 * scale), radius=int(135 * scale), fill=(250, 31, 75, 56))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(int(24 * scale))))

    draw.rounded_rectangle(rounded, radius=int(135 * scale), fill=(255, 29, 76, 255))
    draw.rounded_rectangle(rect(82, 70, 942, 948, scale), radius=int(135 * scale), outline=(255, 72, 112, 140), width=max(1, int(2 * scale)))

    font_bold = load_font(int(165 * scale), bold=True)
    title = "小红书"
    title_box = draw.textbbox((0, 0), title, font=font_bold)
    draw.text(((size - (title_box[2] - title_box[0])) / 2, 150 * scale), title, font=font_bold, fill=(255, 255, 255, 255))

    for idx, x in enumerate([514, 584, 654]):
        alpha = [235, 180, 130][idx]
        draw.rounded_rectangle(
            rect(x, 390 + idx * 28, x + 250, 740 + idx * 28, scale),
            radius=int(38 * scale),
            fill=(255, 255, 255, alpha),
        )

    card = rect(280, 360, 638, 780, scale)
    draw.rounded_rectangle(card, radius=int(42 * scale), fill=(255, 255, 255, 248))
    draw.rounded_rectangle(rect(335, 430, 565, 455, scale), radius=int(14 * scale), fill=(255, 82, 120, 190))
    draw.rounded_rectangle(rect(335, 485, 535, 510, scale), radius=int(14 * scale), fill=(255, 126, 151, 140))
    image_box = rect(350, 560, 610, 735, scale)
    draw.rounded_rectangle(image_box, radius=int(24 * scale), fill=(255, 229, 234, 255))
    draw.polygon(points([(365, 690), (450, 610), (525, 700), (570, 645), (610, 705), (610, 735), (365, 735)], scale), fill=(255, 126, 151, 220))
    draw.ellipse(rect(512, 585, 555, 628, scale), fill=(255, 103, 134, 205))

    button_center = (720 * scale, 660 * scale)
    draw.ellipse(rect(630, 570, 810, 750, scale), fill=(255, 31, 76, 255), outline=(255, 150, 168, 185), width=max(2, int(3 * scale)))
    draw.line(points([(720, 615), (720, 690)], scale), fill=(255, 255, 255, 255), width=int(28 * scale))
    draw.polygon(points([(680, 665), (720, 705), (760, 665)], scale), fill=(255, 255, 255, 255))
    draw.rounded_rectangle(rect(675, 722, 765, 742, scale), radius=int(10 * scale), fill=(255, 255, 255, 255))

    draw.rounded_rectangle(rect(85, 722, 940, 945, scale), radius=int(100 * scale), fill=(255, 255, 255, 250))
    crawl_font = load_font(int(105 * scale), bold=True)
    crawl = "批量爬取"
    crawl_box = draw.textbbox((0, 0), crawl, font=crawl_font)
    draw.text(((size - (crawl_box[2] - crawl_box[0])) / 2, 740 * scale), crawl, font=crawl_font, fill=(24, 23, 38, 255))
    note_font = load_font(int(50 * scale), bold=True)
    note = "· 小红书笔记 ·"
    note_box = draw.textbbox((0, 0), note, font=note_font)
    draw.text(((size - (note_box[2] - note_box[0])) / 2, 870 * scale), note, font=note_font, fill=(255, 44, 84, 255))

    return canvas


def rect(left: float, top: float, right: float, bottom: float, scale: float) -> tuple[int, int, int, int]:
    return (int(left * scale), int(top * scale), int(right * scale), int(bottom * scale))


def offset(box: tuple[int, int, int, int], dx: float, dy: float) -> tuple[int, int, int, int]:
    return (int(box[0] + dx), int(box[1] + dy), int(box[2] + dx), int(box[3] + dy))


def points(values: list[tuple[float, float]], scale: float) -> list[tuple[int, int]]:
    return [(int(x * scale), int(y * scale)) for x, y in values]


def load_font(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


if __name__ == "__main__":
    raise SystemExit(main())

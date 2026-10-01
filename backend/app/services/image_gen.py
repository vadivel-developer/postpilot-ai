"""Branded LinkedIn image generation with Pillow. Original, template-drawn layouts — never a copy of
the source video's thumbnail. Text is measured and wrapped to fit its box exactly; if the content
genuinely cannot fit even at the smallest allowed size, generation fails with a clear error instead
of silently overlapping or clipping text.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import IMAGES_DIR

FONT_DIR = Path(__file__).parent / "fonts"
DEFAULT_SIZE = (1200, 1200)
MARGIN = 90
MAX_TAKEAWAYS = 3


class ImageGenerationError(Exception):
    pass


@dataclass
class BrandSpec:
    brand_name: str
    footer: str
    color_primary: str
    color_secondary: str
    color_text: str
    template: str = "classic"  # "classic" | "minimal"


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    name = {"bold": "Roboto-Bold.ttf", "medium": "Roboto-Medium.ttf", "regular": "Roboto-Regular.ttf"}[weight]
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _hard_break(draw: ImageDraw.ImageDraw, word: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Breaks a single token with no spaces (a URL, a run of characters) that is wider than
    max_width on its own — otherwise it would run off the edge of the image untouched."""
    pieces: list[str] = []
    chunk = ""
    for ch in word:
        candidate = chunk + ch
        if draw.textlength(candidate, font=font) <= max_width or not chunk:
            chunk = candidate
        else:
            pieces.append(chunk)
            chunk = ch
    if chunk:
        pieces.append(chunk)
    return pieces


def _wrap_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if draw.textlength(word, font=font) <= max_width:
            current = word
        else:
            broken = _hard_break(draw, word, font, max_width)
            lines.extend(broken[:-1])
            current = broken[-1] if broken else ""
    if current:
        lines.append(current)
    return lines or [""]


def _fit_text_block(draw: ImageDraw.ImageDraw, text: str, weight: str, max_width: int, max_height: int, start_size: int, min_size: int) -> tuple[list[str], ImageFont.FreeTypeFont, int]:
    """Shrinks font size until the wrapped text fits max_height; raises if even min_size overflows."""
    size = start_size
    while size >= min_size:
        font = _font(weight, size)
        lines = _wrap_to_width(draw, text, font, max_width)
        line_height = int(size * 1.28)
        total_height = line_height * len(lines)
        if total_height <= max_height:
            return lines, font, line_height
        size -= 2
    raise ImageGenerationError(f"'{text[:40]}...' does not fit even at the minimum font size — shorten the text.")


def generate_linkedin_image(*, headline: str, takeaways: list[str], brand: BrandSpec, out_path: Path | None = None, size: tuple[int, int] = DEFAULT_SIZE) -> Path:
    if not headline.strip():
        raise ImageGenerationError("A headline is required.")
    takeaways = [t.strip() for t in takeaways if t.strip()][:MAX_TAKEAWAYS]

    width, height = size
    img = Image.new("RGB", size, brand.color_primary)
    draw = ImageDraw.Draw(img)

    if brand.template == "minimal":
        draw.rectangle([0, 0, width, height], fill="#FFFFFF")
        draw.rectangle([0, 0, width, 18], fill=brand.color_secondary)
        headline_color = brand.color_primary
        body_color = "#222222"
    else:
        draw.rectangle([0, 0, width, height], fill=brand.color_primary)
        draw.rectangle([0, height - 220, width, height], fill=brand.color_secondary)
        headline_color = brand.color_text
        body_color = brand.color_text

    content_width = width - 2 * MARGIN
    y = MARGIN + 30

    headline_area_h = int(height * 0.32)
    lines, font, line_h = _fit_text_block(draw, headline, "bold", content_width, headline_area_h, start_size=64, min_size=34)
    for line in lines:
        draw.text((MARGIN, y), line, font=font, fill=headline_color)
        y += line_h
    y += 30

    body_bottom_limit = height - 240 if brand.template == "classic" else height - 160
    remaining_h = body_bottom_limit - y
    if takeaways and remaining_h > 60:
        per_item_budget = max(60, remaining_h // max(1, len(takeaways)))
        bullet_font_start = min(34, max(20, per_item_budget // 2))
        for item in takeaways:
            if y >= body_bottom_limit - 20:
                break
            budget = min(per_item_budget, body_bottom_limit - y)
            item_lines, item_font, item_line_h = _fit_text_block(draw, item, "medium", content_width - 50, budget, start_size=bullet_font_start, min_size=18)
            bullet_y = y + (item_font.size - 20)
            draw.ellipse([MARGIN, bullet_y, MARGIN + 16, bullet_y + 16], fill=body_color)
            for i, line in enumerate(item_lines):
                draw.text((MARGIN + 40, y + i * item_line_h), line, font=item_font, fill=body_color)
            y += item_line_h * len(item_lines) + 14

    footer_font = _font("regular", 26)
    brand_font = _font("bold", 30)
    if brand.template == "classic":
        draw.text((MARGIN, height - 170), brand.brand_name, font=brand_font, fill=brand.color_text)
        draw.text((MARGIN, height - 120), brand.footer, font=footer_font, fill=brand.color_text)
    else:
        draw.text((MARGIN, height - 110), brand.brand_name, font=brand_font, fill=brand.color_primary)
        draw.text((MARGIN, height - 70), brand.footer, font=footer_font, fill="#555555")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = out_path or (IMAGES_DIR / f"card_{abs(hash((headline, tuple(takeaways))))}.png")
    img.save(out_path, "PNG")
    return out_path

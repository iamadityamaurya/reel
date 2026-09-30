"""Cover / thumbnail generation: an existing image with the title overlaid."""

import logging
from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)


def _load_font(size: int):
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, draw: ImageDraw.ImageDraw, font, max_width: int, stroke_width: int) -> List[str]:
    """Greedily wrap ``text`` to fit ``max_width`` pixels."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke_width)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class CoverGenerator:
    @staticmethod
    def create_cover(
        base_image: Path,
        title: str,
        output_path: Path,
        width: int = 1080,
        height: int = 1920,
    ) -> Path:
        """
        Build a cover image from ``base_image`` with ``title`` text over the lower
        half, darkened with a vertical gradient so the text stays readable.
        """
        base = Image.open(base_image).convert("RGB")
        base = ImageOps.fit(base, (width, height), method=Image.LANCZOS)
        img = base.convert("RGBA")

        # Vertical gradient: transparent up top, dark toward the bottom.
        gradient = Image.new("L", (1, height))
        fade_start = int(height * 0.30)
        for y in range(height):
            if y < fade_start:
                alpha = 0
            else:
                alpha = int(215 * (y - fade_start) / max(1, height - fade_start))
            gradient.putpixel((0, y), min(alpha, 215))
        gradient = gradient.resize((width, height))
        shade = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        shade.putalpha(gradient)
        img = Image.alpha_composite(img, shade)

        draw = ImageDraw.Draw(img)
        font = _load_font(96)
        stroke = 6
        lines = _wrap_text(title, draw, font, int(width * 0.86), stroke)
        text = "\n".join(lines)

        bbox = draw.multiline_textbbox(
            (0, 0), text, font=font, spacing=20, align="center", stroke_width=stroke
        )
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (width - text_w) / 2 - bbox[0]
        y = height * 0.66 - text_h / 2 - bbox[1]

        draw.multiline_text(
            (x, y),
            text,
            font=font,
            fill=(255, 255, 255, 255),
            spacing=20,
            align="center",
            stroke_width=stroke,
            stroke_fill=(0, 0, 0, 255),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(output_path, "JPEG", quality=92)
        logger.info(f"Cover image written to {output_path}")
        return output_path

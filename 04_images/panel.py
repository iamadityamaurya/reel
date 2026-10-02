"""Character panels and vertical stacking for the split-screen layout.

The split layout shows the two characters in the top part of the frame and a
looping background clip (e.g. gameplay footage) in the bottom part. This module
builds the top panel: it tracks the characters in a source image, crops away the
empty background and fits them onto a clean canvas, optionally with a title
header, so the characters look large and centred instead of tiny with lots of
whitespace.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

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


def _wrap_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
    stroke: int,
) -> list:
    """Greedily wrap ``text`` so each line fits within ``max_width`` pixels."""
    words = text.split()
    lines: list = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    y_top: int,
    y_bottom: int,
    max_size: int,
    min_size: int,
    fill: Tuple[int, int, int] = (255, 255, 255),
    max_lines: int = 3,
    stroke_fill: Tuple[int, int, int] = (0, 0, 0),
    use_badge: bool = True,
) -> None:
    """
    Draw ``text`` centered horizontally as a title hook badge card, auto-shrinking/wrapping
    it to fit within the box ``[y_top, y_bottom]`` and ``90%`` of ``width``.
    """
    if not text:
        return
    max_w = int(width * 0.90)
    max_h = y_bottom - y_top
    size = max_size
    lines: list = [text]
    font = _load_font(size)
    spacing = max(4, size // 8)

    while size >= min_size:
        font = _load_font(size)
        spacing = max(4, size // 8)
        words = text.split()
        lines = []
        curr = ""
        for w in words:
            cand = f"{curr} {w}".strip()
            bbox = draw.textbbox((0, 0), cand, font=font)
            if bbox[2] - bbox[0] <= max_w - 60 or not curr:
                curr = cand
            else:
                lines.append(curr)
                curr = w
        if curr:
            lines.append(curr)

        body = "\n".join(lines)
        bbox = draw.multiline_textbbox((0, 0), body, font=font, spacing=spacing, align="center")
        total_h = bbox[3] - bbox[1]
        if len(lines) <= max_lines and total_h <= max_h - 24:
            break
        size -= 2

    body = "\n".join(lines)
    bbox = draw.multiline_textbbox((0, 0), body, font=font, spacing=spacing, align="center")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    if use_badge:
        pad_x = 36
        pad_y = 16
        card_w = text_w + pad_x * 2
        card_h = text_h + pad_y * 2
        card_x0 = (width - card_w) // 2
        card_y0 = y_top + (max_h - card_h) // 2
        card_x1 = card_x0 + card_w
        card_y1 = card_y0 + card_h

        draw.rounded_rectangle(
            [card_x0, card_y0, card_x1, card_y1],
            radius=18,
            fill=(15, 23, 42),      # Dark slate container
            outline=(51, 65, 85),   # Soft accent border
            width=3,
        )
        text_x = card_x0 + (card_w - text_w) // 2 - bbox[0]
        text_y = card_y0 + (card_h - text_h) // 2 - bbox[1]
        draw.multiline_text(
            (text_x, text_y),
            body,
            font=font,
            fill=(255, 255, 255),
            spacing=spacing,
            align="center",
        )
    else:
        text_x = (width - text_w) // 2 - bbox[0]
        text_y = y_top + (max_h - text_h) // 2 - bbox[1]
        draw.multiline_text(
            (text_x, text_y),
            body,
            font=font,
            fill=fill,
            spacing=spacing,
            align="center",
            stroke_width=max(2, size // 16),
            stroke_fill=stroke_fill,
        )


def content_bbox(
    image: Image.Image,
    threshold: int = 235,
    downscale_width: int = 384,
) -> Tuple[int, int, int, int]:
    """
    Return the bounding box of the non-background content in ``image``.

    The storyboard images are drawn on a near-white background, so we threshold a
    downscaled grayscale copy (fast, and unaffected by a faint gradient) and take
    the extent of the darker pixels. Returns the full image box when nothing is
    detected.
    """
    gray = image.convert("L")
    width, height = gray.size
    scale = downscale_width / width
    small = gray.resize((downscale_width, max(1, int(height * scale))), Image.BILINEAR)
    bbox = small.point(lambda p: 255 if p < threshold else 0).getbbox()
    if bbox is None:
        return (0, 0, width, height)
    left, top, right, bottom = bbox
    return (
        max(0, int(left / scale)),
        max(0, int(top / scale)),
        min(width, int(right / scale)),
        min(height, int(bottom / scale)),
    )


def build_character_panel(
    image_path: Path,
    width: int,
    height: int,
    title: Optional[str] = None,
    title_size: Optional[int] = None,
    content_scale: float = 0.94,
    padding_frac: float = 0.02,
    background: Tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """
    Build a ``width`` x ``height`` panel with the characters from ``image_path``
    cropped to their content, scaled to fit and anchored to the bottom edge.

    ``title`` draws a bold header badge at the top (kept clear of the characters).
    """
    image = Image.open(image_path).convert("RGB")
    left, top, right, bottom = content_bbox(image)
    if right - left < 10 or bottom - top < 10:
        left, top, right, bottom = 0, 0, image.width, image.height

    pad_x = int((right - left) * padding_frac)
    pad_y = int((bottom - top) * padding_frac)
    crop = image.crop((
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(image.width, right + pad_x),
        min(image.height, bottom + pad_y),
    ))

    panel = Image.new("RGB", (width, height), background)

    header = int(height * 0.20) if title else 0
    avail_w = int(width * 0.94)
    avail_h = int((height - header) * content_scale)
    scale = min(avail_w / crop.width, avail_h / crop.height)
    crop_w = max(1, int(crop.width * scale))
    crop_h = max(1, int(crop.height * scale))
    crop = crop.resize((crop_w, crop_h), Image.LANCZOS)
    # Anchor to the bottom so the characters look like they are standing on the
    # divider between the two halves.
    panel.paste(crop, ((width - crop_w) // 2, height - crop_h))

    if title:
        draw = ImageDraw.Draw(panel)
        _draw_text_block(
            draw, title, width,
            0, header,
            title_size or max(44, int(height * 0.065)), 28, (255, 255, 255),
            use_badge=True,
        )

    return panel


def fit_cover(image_path: Path, size: Tuple[int, int]) -> Image.Image:
    """Open ``image_path`` and center-crop/scale it to exactly ``size``."""
    image = Image.open(image_path).convert("RGB")
    return ImageOps.fit(image, size, method=Image.LANCZOS)


def stack_vertical(
    top_image: Image.Image,
    bottom_image: Image.Image,
    output_path: Path,
    quality: int = 92,
    title: Optional[str] = None,
) -> Path:
    """Stack two same-width images vertically and save the result as JPEG."""
    width = top_image.width
    total_height = top_image.height + bottom_image.height
    canvas = Image.new("RGB", (width, total_height), (0, 0, 0))
    canvas.paste(top_image, (0, 0))
    canvas.paste(bottom_image, (0, top_image.height))

    if title:
        draw = ImageDraw.Draw(canvas)
        _draw_text_block(
            draw,
            title,
            width,
            y_top=0,
            y_bottom=total_height,
            max_size=44,
            min_size=28,
            use_badge=True,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "JPEG", quality=quality)
    logger.info(f"Stacked cover written to {output_path}")
    return output_path

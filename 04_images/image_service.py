"""Default character avatar generation."""

import logging
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class ImageManager:
    @staticmethod
    def create_default_avatar(name: str, color: Tuple[int, int, int], pose_label: str, output_path: Path):
        """Generates a clean vector-like placeholder avatar PNG if user hasn't uploaded custom images."""
        w, h = 400, 700
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw character silhouette / body representation
        # Head
        draw.ellipse([140, 60, 260, 180], fill=color)
        # Body
        draw.rounded_rectangle([110, 190, 290, 480], radius=30, fill=color)
        # Legs
        draw.rectangle([130, 480, 180, 660], fill=color)
        draw.rectangle([220, 480, 270, 660], fill=color)

        # Pose specific details
        if "pocket" in pose_label.lower():
            # One hand in pocket indication
            draw.rectangle([90, 320, 120, 420], fill=color)
        else:
            # Thinking pose hand near head
            draw.line([(290, 320), (320, 200), (250, 150)], fill=color, width=25)

        # Text Label
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 28)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), name, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, 660), name, fill=(40, 40, 40), font=font)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
        return output_path

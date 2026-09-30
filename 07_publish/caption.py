"""LLM-generated Instagram caption (with hashtags) for a generated reel."""

import logging
from typing import Optional

from groq import Groq

import config
from utils import clean_text, retry_call

logger = logging.getLogger(__name__)

# Instagram captions are capped at 2200 characters.
_MAX_CAPTION_CHARS = 2200


class CaptionService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.client = (
            Groq(api_key=self.api_key, max_retries=0, timeout=60.0)
            if self.api_key else None
        )

    def generate_caption(self, title: str, summary: str = "") -> str:
        """Generate a short, engaging caption followed by relevant hashtags."""
        if self.client is None:
            logger.warning("GROQ_API_KEY is not set; using fallback caption.")
            return self.fallback_caption(title)

        prompt = f"""Write an Instagram Reels caption for a short two-person educational video.
Title: {title}
Summary: {summary}

Rules:
- Write 1 to 2 short, punchy sentences that make people want to watch.
- Use simple, everyday words. Avoid jargon.
- Do NOT use long dashes (em dash or en dash). Use a plain hyphen or a comma.
- After the sentences, add a blank line, then 10 to 15 relevant lowercase hashtags separated by spaces.
- Do not use markdown, quotes, or surrounding explanation.

Return ONLY the caption text."""

        try:
            response = retry_call(
                lambda: self.client.chat.completions.create(
                    model=config.GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                ),
                attempts=3,
                base_delay=2.0,
                description="Groq caption generation",
            )
            caption = clean_text(response.choices[0].message.content.strip())
        except Exception as e:
            logger.exception("Groq caption generation failed.")
            raise RuntimeError(f"Failed to generate caption via Groq: {e}") from e

        if len(caption) > _MAX_CAPTION_CHARS:
            caption = caption[: _MAX_CAPTION_CHARS - 3].rstrip() + "..."
        return caption

    @staticmethod
    def fallback_caption(title: str) -> str:
        """Simple caption used when the LLM is unavailable."""
        hashtags = (
            "#reels #shorts #learn #tech #ai #coding #programming "
            "#devops #explained #techtips"
        )
        return f"{clean_text(title)} - explained in 30 seconds.\n\n{hashtags}"

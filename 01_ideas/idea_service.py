import json
import logging
from typing import List, Dict, Any, Optional

from groq import Groq

import config
from utils import retry_call

logger = logging.getLogger(__name__)

class IdeaService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY
        self.client = (
            Groq(api_key=self.api_key, max_retries=0, timeout=60.0)
            if self.api_key else None
        )

    def generate_ideas(self, topic: str = "", tone: str = "educational", count: int = 5) -> List[Dict[str, Any]]:
        if self.client is None:
            logger.warning(
                "GROQ_API_KEY is not set; returning offline placeholder ideas."
            )
            # Fallback mock ideas if key missing
            return [
                {"id": 1, "title": f"{topic or 'AI'} Concept #1", "hook": "Did you know this crazy fact?", "summary": "A deep dive into key differences."},
                {"id": 2, "title": f"{topic or 'Tech'} Debate #2", "hook": "Why everyone gets this wrong!", "summary": "Clarifying popular misconceptions."}
            ]

        prompt = f"""Generate {count} engaging video ideas for a two-person conversational reel/video.
Topic: {topic if topic else 'Interesting tech, programming, AI, or science topic'}
Tone: {tone}

Return ONLY a valid JSON list of objects matching this schema:
[
  {{
    "id": 1,
    "title": "Short Catchy Title",
    "hook": "Opening hook line",
    "summary": "Brief explanation of what Character A and B discuss."
  }}
]
Do not include markdown backticks or extra text outside JSON.
"""
        try:
            response = retry_call(
                lambda: self.client.chat.completions.create(
                    model=config.GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    response_format={"type": "json_object"} if "json" in config.GROQ_MODEL else None,
                ),
                attempts=3,
                base_delay=2.0,
                description="Groq idea generation",
            )

            raw = response.choices[0].message.content.strip()
            # Clean possible markdown formatting
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "ideas" in parsed:
                return parsed["ideas"]
            elif isinstance(parsed, list):
                return parsed
            return [parsed]
        except Exception as e:
            logger.exception("Groq idea generation failed.")
            raise RuntimeError(f"Failed to generate ideas via Groq: {e}") from e

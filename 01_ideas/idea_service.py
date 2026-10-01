import json
import logging
from typing import Any, Dict, List, Optional

import httpx

import config
from utils import retry_call

logger = logging.getLogger(__name__)


class IdeaService:
    """Generates reel ideas with the Google Gemini API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.model = model or config.GEMINI_MODEL
        self.base_url = config.GEMINI_API_BASE.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate_ideas(
        self, topic: str = "", tone: str = "educational", count: int = 5
    ) -> List[Dict[str, Any]]:
        if not self.is_configured:
            logger.warning(
                "GEMINI_API_KEY is not set; returning offline placeholder ideas."
            )
            return [
                {"id": 1, "title": f"{topic or 'AI'} Concept #1", "hook": "Did you know this crazy fact?", "summary": "A deep dive into key differences."},
                {"id": 2, "title": f"{topic or 'Tech'} Debate #2", "hook": "Why everyone gets this wrong!", "summary": "Clarifying popular misconceptions."},
            ]

        prompt = f"""Generate {count} engaging video ideas for a two-person conversational reel/video.
Topic: {topic if topic else 'Interesting tech, programming, AI, or science topic'}
Tone: {tone}

Return ONLY a valid JSON object shaped like this:
{{
  "ideas": [
    {{
      "id": 1,
      "title": "Short Catchy Title",
      "hook": "Opening hook line",
      "summary": "Brief explanation of what Character A and B discuss."
    }}
  ]
}}
Write in simple, everyday words. Do NOT use long dashes (em dash or en dash).
Do not include markdown backticks or any text outside the JSON."""

        def _call() -> Dict[str, Any]:
            response = httpx.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.9,
                    },
                },
                timeout=90.0,
            )
            response.raise_for_status()
            return response.json()

        try:
            data = retry_call(
                _call,
                attempts=3,
                base_delay=2.0,
                description="Gemini idea generation",
            )

            candidates = data.get("candidates") or []
            if not candidates:
                feedback = data.get("promptFeedback", {})
                raise RuntimeError(f"Gemini returned no candidates: {feedback}")

            parts = candidates[0].get("content", {}).get("parts", [])
            raw = "".join(part.get("text", "") for part in parts).strip()

            # Clean possible markdown formatting just in case.
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
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except Exception as e:
            logger.exception("Gemini idea generation failed.")
            raise RuntimeError(f"Failed to generate ideas via Gemini: {e}") from e
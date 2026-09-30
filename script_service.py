import json
import logging
from typing import Dict, Any, List, Optional
import config

logger = logging.getLogger(__name__)

class ScriptService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GROQ_API_KEY

    def generate_script(self, idea_title: str, idea_summary: str, duration_sec: int = 30) -> Dict[str, Any]:
        if not self.api_key:
            return self._fallback_script(idea_title)

        try:
            from groq import Groq
            client = Groq(api_key=self.api_key)

            prompt = f"""Write a compelling 2-person conversational video script between Character A and Character B.
Title: {idea_title}
Summary/Context: {idea_summary}
Target Duration: ~{duration_sec} seconds (approx 5 to 10 back-and-forth lines total).

Rules:
- Character A is curious/conversational.
- Character B is knowledgeable/thoughtful.
- Explain everything in simple, everyday words that a complete beginner can understand.
  Avoid jargon. If a technical term is unavoidable, explain it briefly in plain language.
- Keep sentences short, voice-friendly, and natural.
- Do NOT use long dashes (em dash "—" or en dash "–"). Use a plain hyphen "-", a comma,
  or split the sentence into two short sentences instead.
- Start with a strong hook.

Return ONLY valid JSON with this exact structure:
{{
  "title": "{idea_title}",
  "dialogue": [
    {{
      "speaker": "character_a",
      "text": "First hook spoken by Character A",
      "emotion": "curious"
    }},
    {{
      "speaker": "character_b",
      "text": "Response spoken by Character B",
      "emotion": "thoughtful"
    }}
  ]
}}
"""
            response = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            data = json.loads(raw)
            self.validate_script(data)
            data["title"] = self._clean_text(data.get("title", ""))
            for item in data["dialogue"]:
                item["text"] = self._clean_text(item.get("text", ""))
            return data
        except Exception as e:
            logger.error(f"Failed to generate script via Groq: {e}")
            return self._fallback_script(idea_title)

    def validate_script(self, script_data: Dict[str, Any]) -> bool:
        if "title" not in script_data or "dialogue" not in script_data:
            raise ValueError("Script must contain 'title' and 'dialogue' keys.")
        if not isinstance(script_data["dialogue"], list) or len(script_data["dialogue"]) == 0:
            raise ValueError("Script dialogue must be a non-empty list.")
        for item in script_data["dialogue"]:
            if "speaker" not in item or "text" not in item:
                raise ValueError("Dialogue entries must have 'speaker' and 'text'.")
            if item["speaker"] not in ["character_a", "character_b"]:
                item["speaker"] = "character_a" if "a" in item["speaker"].lower() else "character_b"
        return True

    @staticmethod
    def _clean_text(text: Optional[str]) -> str:
        """
        Normalise long dashes and other typographic characters that the LLM may
        still emit. These are hard to pronounce in TTS and can also break caption
        rendering, so they are converted to plain hyphens.
        """
        if not isinstance(text, str):
            return text
        replacements = {
            "\u2014": "-",  # em dash
            "\u2013": "-",  # en dash
            "\u2012": "-",  # figure dash
            "\u2015": "-",  # horizontal bar
            "\u2011": "-",  # non-breaking hyphen
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text.strip()

    def _fallback_script(self, title: str) -> Dict[str, Any]:
        return {
            "title": title,
            "dialogue": [
                {
                    "speaker": "character_a",
                    "text": "Have you ever wondered how AI conversation videos are generated?",
                    "emotion": "curious"
                },
                {
                    "speaker": "character_b",
                    "text": "Absolutely! It turns out Python, Deepgram TTS, and FFmpeg make it super fast.",
                    "emotion": "thoughtful"
                },
                {
                    "speaker": "character_a",
                    "text": "Wait, so we can render vertical 9:16 reels automatically?",
                    "emotion": "surprised"
                },
                {
                    "speaker": "character_b",
                    "text": "Exactly. Synchronized subtitles and side-by-side avatars included!",
                    "emotion": "confident"
                }
            ]
        }

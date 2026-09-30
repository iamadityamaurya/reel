#!/usr/bin/env python3
"""
Generate a batch of two-person conversational reel ideas and save them to JSON.

Examples:
    python generate_ideas.py
    python generate_ideas.py --topic "Docker vs Kubernetes"
    python generate_ideas.py --topic "Python tips" --count 20 --tone technical
    python generate_ideas.py --count 20 --output data/ideas.json
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import config
from idea_service import IdeaService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IdeaGenerator")

_LONG_DASHES = ("\u2014", "\u2013", "\u2012", "\u2015")  # em, en, figure, horizontal bar


def _clean_text(text: str) -> str:
    """Replace long dashes with a spaced hyphen and non-breaking hyphens with '-'."""
    for dash in _LONG_DASHES:
        text = text.replace(dash, " - ")
    text = text.replace("\u2011", "-")  # non-breaking hyphen
    return " ".join(text.split())


def generate_unique_ideas(
    topic: str,
    count: int = 20,
    tone: str = "educational",
    batch_size: int = 5,
) -> List[Dict[str, Any]]:
    """
    Generate up to ``count`` unique ideas.

    Ideas are fetched in small batches and de-duplicated by title, because a
    single LLM call rarely returns a large list exactly as requested.
    """
    service = IdeaService()
    ideas: List[Dict[str, Any]] = []
    seen_titles = set()
    max_attempts = max(4, (count // max(batch_size, 1)) * 3)
    attempts = 0
    empty_streak = 0

    while len(ideas) < count and attempts < max_attempts:
        attempts += 1
        remaining = count - len(ideas)
        request_count = min(batch_size, remaining)
        logger.info("Requesting %d idea(s) (have %d/%d)...", request_count, len(ideas), count)

        batch = service.generate_ideas(topic=topic, tone=tone, count=request_count)

        new_in_batch = 0
        for idea in batch:
            if not isinstance(idea, dict):
                continue
            title = _clean_text(str(idea.get("title", "")))
            key = title.lower()
            if not title or key in seen_titles:
                continue
            seen_titles.add(key)
            idea["id"] = len(ideas) + 1
            idea["title"] = title
            if idea.get("hook"):
                idea["hook"] = _clean_text(str(idea["hook"]))
            if idea.get("summary"):
                idea["summary"] = _clean_text(str(idea["summary"]))
            ideas.append(idea)
            new_in_batch += 1
            if len(ideas) >= count:
                break

        empty_streak = empty_streak + 1 if new_in_batch == 0 else 0
        if empty_streak >= 3:
            logger.warning("Stopped early: no new unique ideas after %d batches.", empty_streak)
            break

    return ideas


def save_ideas(
    ideas: List[Dict[str, Any]],
    topic: str,
    tone: str,
    output_path: Path,
) -> Path:
    """Write the generated ideas to ``output_path`` as formatted JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "topic": topic or "Surprise me (auto)",
        "tone": tone,
        "count": len(ideas),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ideas": ideas,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate reel ideas and save them to a JSON file."
    )
    parser.add_argument("--topic", type=str, default="",
                        help="Topic for the ideas (default: let the AI choose)")
    parser.add_argument("--count", type=int, default=20,
                        help="Number of ideas to generate (default: 20)")
    parser.add_argument("--tone", type=str, default="educational",
                        choices=["educational", "humorous", "informative",
                                 "philosophical", "casual", "technical"],
                        help="Tone of the ideas (default: educational)")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Ideas requested per API call (default: 5)")
    parser.add_argument("--output", type=str, default=str(config.DATA_DIR / "ideas.json"),
                        help="Output JSON file path (default: data/ideas.json)")
    args = parser.parse_args()

    topic_label = args.topic or "auto-selected topics"
    print(f"\n💡 Generating {args.count} idea(s) about '{topic_label}' (tone: {args.tone})...\n")

    ideas = generate_unique_ideas(args.topic, args.count, args.tone, args.batch_size)

    if not ideas:
        logger.error("No ideas were generated.")
        return

    output_path = save_ideas(ideas, args.topic, args.tone, args.output)
    print(f"\n✅ Saved {len(ideas)} idea(s) to {output_path.resolve()}\n")
    for idea in ideas:
        print(f"  {idea['id']:>2}. {idea.get('title', '')}")
        if idea.get("hook"):
            print(f"      hook: {idea['hook']}")


if __name__ == "__main__":
    main()

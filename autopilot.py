#!/usr/bin/env python3
"""
Autopilot: automatically render and publish one reel per cycle.

Each cycle:
  1. Picks the next idea from Supabase with ``video_generated = false``,
     starting at ``index`` 1 and moving upward.
  2. Runs the full pipeline on it (script, voice, subtitles, video, publish)
     using the photo/01 storyboard and the split-screen layout by default.
  3. Marks that idea row as ``video_generated = true``.

Cycles are spaced by a random interval between 1h 00m and 1h 10m.

Usage:
    python3 autopilot.py                      # run forever
    python3 autopilot.py --once               # run a single cycle, then exit
    python3 autopilot.py --dry-run            # show the next idea, change nothing
    python3 autopilot.py --min-minutes 60 --max-minutes 70
    python3 autopilot.py --photo-set 01
    python3 autopilot.py --layout full         # opt out of the split layout
"""

import argparse
import importlib
import logging
import random
import sys
import time
from pathlib import Path

# Make the numbered stage packages importable no matter where this is run from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

SupabaseIdeaStore = getattr(
    importlib.import_module("01_ideas.supabase_store"), "SupabaseIdeaStore"
)
SupabaseTableMissingError = getattr(
    importlib.import_module("01_ideas.supabase_store"), "SupabaseTableMissingError"
)
IdeaService = getattr(
    importlib.import_module("01_ideas.idea_service"), "IdeaService"
)
run_pipeline = getattr(importlib.import_module("main"), "run_pipeline")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Autopilot")


def fetch_next_idea(store) -> "dict | None":
    idea = None
    try:
        idea = store.next_unprocessed_idea()
    except Exception as e:
        logger.warning("Transient network error fetching idea from Supabase: %s. Retrying in 5s...", e)
        time.sleep(5)
        try:
            idea = store.next_unprocessed_idea()
        except Exception as e2:
            logger.error("Could not fetch idea from Supabase after retry: %s", e2)
            idea = None

    # Verify video_generated is false; if true, skip to prevent repeating ideas
    if idea and idea.get("video_generated"):
        logger.warning(
            "Idea #%s has video_generated=true; skipping to find an unprocessed idea...",
            idea.get("index"),
        )
        idea = None

    if not idea:
        logger.info(
            "💡 No unprocessed ideas (video_generated=false) left in Supabase. Auto-generating a fresh batch..."
        )
        try:
            idea_svc = IdeaService()
            new_ideas = idea_svc.generate_ideas(
                topic="Interesting tech, programming, AI, or science topic",
                tone="educational",
                count=5,
            )
            if new_ideas:
                saved = store.save_ideas(new_ideas, topic="Auto-Generated", tone="educational")
                if saved:
                    logger.info("🗄️ Saved %d new idea(s) to Supabase table '%s'.", len(saved), store.table)
                    idea = store.next_unprocessed_idea()
                else:
                    idea = new_ideas[0]
        except Exception as e:
            logger.warning("Could not auto-generate new ideas: %s", e)

    return idea


def run_once(photo_set: str = "01", layout: str = "split") -> bool:
    """Run a single cycle. Returns True if a reel was produced."""
    store = SupabaseIdeaStore()

    if not store.is_configured:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in reel/.env."
        )

    idea = fetch_next_idea(store)
    if not idea:
        return False

    row_id = idea.get("id")
    index = idea.get("index")
    title = idea.get("title", "")
    topic = idea.get("topic") or title or "reel"
    logger.info("▶️  Idea #%s: %s", index, title)

    logger.info(
        "🎬 Rendering reel for idea #%s using photo set '%s' (layout: %s)...",
        index, photo_set, layout,
    )
    state = run_pipeline(topic=topic, idea=idea, photo_set=photo_set, layout=layout)
    video_path = state.get("video_path")
    logger.info("✅ Finished idea #%s. Video: %s", index, video_path)

    # Mark the row so the next cycle moves on to the following idea.
    if row_id:
        if store.mark_video_generated(row_id, True):
            logger.info("🗄️  Marked idea #%s as video_generated=true.", index)
        else:
            logger.warning("Could not update video_generated for idea #%s.", index)
    else:
        logger.warning("Idea #%s has no row id; cannot update Supabase.", index)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automatically render and publish reels from Supabase ideas."
    )
    parser.add_argument("--min-minutes", type=float, default=60.0,
                        help="Minimum wait between cycles in minutes (default: 60)")
    parser.add_argument("--max-minutes", type=float, default=70.0,
                        help="Maximum wait between cycles in minutes (default: 70)")
    parser.add_argument("--photo-set", type=str, default="01",
                        help="Storyboard folder under photo/ to use (default: 01)")
    parser.add_argument("--layout", type=str, default="split", choices=["full", "split"],
                        help="Video layout (default: split, i.e. characters on top and gameplay below)")
    parser.add_argument("--once", action="store_true",
                        help="Run a single cycle and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show the next idea without rendering or updating anything")
    args = parser.parse_args()

    if not config.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set; idea generation would fall back to placeholders.")
    if args.max_minutes < args.min_minutes:
        args.max_minutes = args.min_minutes

    if args.dry_run:
        store = SupabaseIdeaStore()
        if not store.is_configured:
            logger.error("Supabase is not configured. Set SUPABASE_URL / SUPABASE_SERVICE_KEY in .env.")
            return 1
        try:
            idea = fetch_next_idea(store)
        except SupabaseTableMissingError as e:
            logger.error("%s", e)
            return 1
        if idea:
            logger.info(
                "Next idea -> index=%s | title=%s | video_generated=%s",
                idea.get("index"), idea.get("title"), idea.get("video_generated"),
            )
        return 0

    logger.info(
        "🚀 Autopilot started. Interval %.0f-%.0f min, photo set '%s', layout '%s'.",
        args.min_minutes, args.max_minutes, args.photo_set, args.layout,
    )

    while True:
        try:
            run_once(photo_set=args.photo_set, layout=args.layout)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            return 0
        except SupabaseTableMissingError as e:
            logger.error("%s", e)
            return 1
        except Exception:
            logger.exception("Cycle failed; will try again next interval.")

        if args.once:
            return 0

        wait_minutes = random.uniform(args.min_minutes, args.max_minutes)
        logger.info("😴 Sleeping %.1f minutes until the next reel...", wait_minutes)
        try:
            time.sleep(wait_minutes * 60)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Telegram control bot for the Supabase-backed reel pipeline."""

import asyncio
import importlib
import logging
from typing import Any, Dict, Optional

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config

SupabaseIdeaStore = getattr(
    importlib.import_module("01_ideas.supabase_store"), "SupabaseIdeaStore"
)
run_pipeline = getattr(importlib.import_module("main"), "run_pipeline")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TelegramBot")

_render_lock = asyncio.Lock()
_active_job: Optional[Dict[str, Any]] = None
_pending_ideas: list[Dict[str, Any]] = []
_pending_topic = ""

_GENERATE_BUTTON = "Generate Ideas"
_VIEW_BUTTON = "View Ideas"
_NEXT_BUTTON = "Next Idea"
_MAKE_NEXT_BUTTON = "Make Next Reel"
_CUSTOM_BUTTON = "Make Custom Topic"
_STATUS_BUTTON = "Status"
_CANCEL_BUTTON = "Cancel"


def _keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [_GENERATE_BUTTON, _VIEW_BUTTON],
            [_NEXT_BUTTON, _MAKE_NEXT_BUTTON],
            [_CUSTOM_BUTTON, _STATUS_BUTTON],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _selection_keyboard() -> ReplyKeyboardMarkup:
    buttons = [f"Save #{number}" for number in range(1, len(_pending_ideas) + 1)]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    rows.append([_CANCEL_BUTTON])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def _allowed(update: Update) -> bool:
    if not update.effective_user or not config.ALLOWED_USER_ID:
        return False
    return str(update.effective_user.id) == str(config.ALLOWED_USER_ID).strip()


async def _authorized(update: Update) -> bool:
    if _allowed(update):
        return True
    if update.effective_message:
        await update.effective_message.reply_text("Unauthorized.")
    return False


def _store() -> Any:
    store = SupabaseIdeaStore()
    if not store.is_configured:
        raise RuntimeError("Supabase is not configured in .env.")
    return store


def _idea_label(idea: Dict[str, Any]) -> str:
    status = "done" if idea.get("video_generated") is True else "pending"
    return f"#{idea.get('index', '?')} [{status}] {idea.get('title', '(untitled)')}"


def _next_idea(store: Any) -> Optional[Dict[str, Any]]:
    ideas = store.list_ideas(
        limit=1000,
        video_generated=None,
        order="index.asc,created_at.asc",
    )
    return next(
        (idea for idea in ideas if idea.get("video_generated") is not True),
        None,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    await update.effective_message.reply_text(
        "Choose an action from the keyboard below.\n\n"
        "You can also use /generate, /save, /ideas, /next, /make_next, /make, or /status.",
        reply_markup=_keyboard(),
    )


async def _generate_topic(update: Update, topic: str) -> None:
    global _pending_ideas, _pending_topic
    try:
        idea_service = getattr(
            importlib.import_module("01_ideas.idea_service"), "IdeaService"
        )
        generated = await asyncio.to_thread(
            lambda: idea_service().generate_ideas(topic=topic, count=5)
        )
        _pending_ideas = [idea for idea in generated if isinstance(idea, dict)]
        _pending_topic = topic
        if not _pending_ideas:
            await update.effective_message.reply_text("No ideas were generated.")
            return
        lines = ["Generated ideas (not saved):"]
        for number, idea in enumerate(_pending_ideas, start=1):
            lines.append(f"\n{number}. {idea.get('title', '(untitled)')}")
            if idea.get("hook"):
                lines.append(f"Hook: {idea['hook']}")
            if idea.get("summary"):
                lines.append(f"Summary: {idea['summary']}")
        lines.append("\nUse /save <number> to save one to Supabase.")
        await update.effective_message.reply_text(
            "\n".join(lines)[:4000],
            reply_markup=_selection_keyboard(),
        )
    except Exception:
        logger.exception("Could not generate Telegram ideas")
        await update.effective_message.reply_text(
            "Could not generate ideas. Check the bot logs for details."
        )


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    topic = " ".join(context.args).strip()
    await _generate_topic(
        update,
        topic or "Interesting tech, programming, AI, or science topic",
    )


async def _save_selection(update: Update, selection: int) -> None:
    global _pending_ideas, _pending_topic
    if not _pending_ideas:
        await update.effective_message.reply_text(
            "There are no generated ideas waiting. Choose Generate Ideas first.",
            reply_markup=_keyboard(),
        )
        return
    if selection < 1 or selection > len(_pending_ideas):
        await update.effective_message.reply_text(
            f"Choose a number from 1 to {len(_pending_ideas)}.",
            reply_markup=_selection_keyboard(),
        )
        return
    selected = _pending_ideas[selection - 1]
    try:
        saved = await asyncio.to_thread(
            lambda: _store().save_ideas(
                [selected], topic=_pending_topic, tone="educational"
            )
        )
        if not saved:
            raise RuntimeError("Supabase did not return a saved row.")
        saved_idea = saved[0]
        _pending_ideas = []
        _pending_topic = ""
        await update.effective_message.reply_text(
            f"Saved to Supabase:\n{_idea_label(saved_idea)}\n\n"
            "Choose Make Next Reel when you want to render it.",
            reply_markup=_keyboard(),
        )
    except Exception:
        logger.exception("Could not save Telegram idea")
        await update.effective_message.reply_text(
            "Could not save the idea. Check the bot logs for details.",
            reply_markup=_keyboard(),
        )


async def save_idea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /save 1")
        return
    await _save_selection(update, int(context.args[0]))


async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Reply Keyboard selections and the topic text they request."""
    if not await _authorized(update):
        return
    text = (update.effective_message.text or "").strip()
    awaiting = context.user_data.get("awaiting")

    if text == _CANCEL_BUTTON:
        context.user_data.pop("awaiting", None)
        await update.effective_message.reply_text(
            "Cancelled.", reply_markup=_keyboard()
        )
        return

    if text.startswith("Save #"):
        try:
            selection = int(text.removeprefix("Save #"))
        except ValueError:
            await update.effective_message.reply_text("Choose one of the Save buttons.")
            return
        await _save_selection(update, selection)
        return

    if awaiting == "generate":
        context.user_data.pop("awaiting", None)
        await _generate_topic(
            update,
            text or "Interesting tech, programming, AI, or science topic",
        )
        return
    if awaiting == "custom":
        context.user_data.pop("awaiting", None)
        await _run_render(update, topic=text)
        return

    if text == _GENERATE_BUTTON:
        context.user_data["awaiting"] = "generate"
        await update.effective_message.reply_text(
            "Type a topic for the ideas, or type auto for a surprise topic."
        )
    elif text == _VIEW_BUTTON:
        await ideas(update, context)
    elif text == _NEXT_BUTTON:
        await next_idea(update, context)
    elif text == _MAKE_NEXT_BUTTON:
        await make_next(update, context)
    elif text == _CUSTOM_BUTTON:
        context.user_data["awaiting"] = "custom"
        await update.effective_message.reply_text("Type the topic for the reel.")
    elif text == _STATUS_BUTTON:
        await status(update, context)


async def ideas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    try:
        rows = await asyncio.to_thread(
            lambda: _store().list_ideas(
                limit=1000,
                video_generated=None,
                order="index.asc,created_at.asc",
            )
        )
        message = "\n".join(_idea_label(row) for row in rows) if rows else "No ideas found in Supabase."
        await update.effective_message.reply_text(message[:4000])
    except Exception as error:
        logger.exception("Could not list Supabase ideas")
        await update.effective_message.reply_text(f"Could not fetch ideas: {error}")


async def next_idea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    try:
        idea = await asyncio.to_thread(lambda: _next_idea(_store()))
        await update.effective_message.reply_text(
            _idea_label(idea) if idea else "No pending ideas remain."
        )
    except Exception as error:
        logger.exception("Could not fetch the next idea")
        await update.effective_message.reply_text(f"Could not fetch the next idea: {error}")


def _render_existing_idea(idea: Dict[str, Any]) -> Dict[str, Any]:
    global _active_job
    _active_job = {"title": idea.get("title", ""), "status": "rendering"}
    try:
        state = run_pipeline(
            topic=idea.get("topic") or idea.get("title", "reel"),
            idea=idea,
            photo_set="01",
            layout="split",
        )
        if idea.get("id"):
            _store().mark_video_generated(idea["id"], True)
        _active_job.update({"status": "complete", "video_path": state.get("video_path")})
        return state
    except Exception:
        _active_job["status"] = "failed"
        raise


def _render_new_topic(topic: str) -> Dict[str, Any]:
    store = _store()
    idea_service = getattr(importlib.import_module("01_ideas.idea_service"), "IdeaService")
    generated = idea_service().generate_ideas(topic=topic, count=3)
    saved = store.save_ideas(generated, topic=topic, tone="")
    if not saved:
        raise RuntimeError("The topic was generated but could not be saved to Supabase.")
    return _render_existing_idea(saved[0])


async def _run_render(
    update: Update,
    idea: Optional[Dict[str, Any]] = None,
    topic: str = "",
) -> None:
    global _active_job
    if _render_lock.locked():
        await update.effective_message.reply_text("A reel is already rendering. Use /status.")
        return
    async with _render_lock:
        await update.effective_message.reply_text("Render started. I will send the result when it finishes.")
        try:
            if idea:
                state = await asyncio.to_thread(_render_existing_idea, idea)
            else:
                state = await asyncio.to_thread(_render_new_topic, topic)
            publish_result = state.get("publish_result") or {}
            published_url = publish_result.get("permalink") or publish_result.get("public_url")
            result_line = f"Published: {published_url}\n" if published_url else ""
            await update.effective_message.reply_text(
                f"Reel complete.\nJob: {state.get('job_id', 'unknown')}\n"
                f"{result_line}"
                f"Video: {state.get('video_path', 'not available')}"
            )
        except Exception:
            logger.exception("Telegram render failed")
            await update.effective_message.reply_text(
                "Render failed. Check the bot logs for the detailed error."
            )
        finally:
            _active_job = None


async def make_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    try:
        idea = await asyncio.to_thread(lambda: _next_idea(_store()))
    except Exception:
        logger.exception("Could not fetch the next idea")
        await update.effective_message.reply_text(
            "Could not fetch the next idea. Check the bot logs for details."
        )
        return
    if not idea:
        await update.effective_message.reply_text("No pending ideas remain in Supabase.")
        return
    await update.effective_message.reply_text(f"Selected {_idea_label(idea)}")
    await _run_render(update, idea=idea)


async def make(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    topic = " ".join(context.args).strip()
    if not topic:
        await update.effective_message.reply_text("Usage: /make Docker vs Kubernetes")
        return
    await _run_render(update, topic=topic)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    if _active_job:
        await update.effective_message.reply_text(
            f"Active render: {_active_job.get('title', '')}\nStatus: {_active_job.get('status')}"
        )
    else:
        await update.effective_message.reply_text("No active render.")


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing from .env.")
    if not config.ALLOWED_USER_ID:
        raise RuntimeError("ALLOWED_USER_ID is missing from .env.")

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("ideas", ideas))
    application.add_handler(CommandHandler("generate", generate))
    application.add_handler(CommandHandler("save", save_idea))
    application.add_handler(CommandHandler("next", next_idea))
    application.add_handler(CommandHandler("make_next", make_next))
    application.add_handler(CommandHandler("make", make))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, button_router)
    )
    application.run_polling()


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
CLI & Modular Orchestrator for AI Two-Person Conversation Video Generator
Run this script end-to-end to generate complete conversational reels!
"""

import sys
import random
import argparse
import logging
import asyncio
import importlib
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import config
from workflow_manager import WorkflowManager


def _load(module_path: str, name: str):
    """Import a numbered stage package (e.g. "01_ideas.idea_service")."""
    return getattr(importlib.import_module(module_path), name)


_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")
_VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv", ".webm", ".m4v")


def discover_gameplay_videos(video_root: Optional[Path] = None) -> List[Path]:
    """Return every background clip under video/ (used by the split layout)."""
    video_root = video_root or config.GAMEPLAY_DIR
    if not video_root.is_dir():
        return []
    return sorted(
        p for p in video_root.iterdir()
        if p.is_file() and p.suffix.lower() in _VIDEO_SUFFIXES
    )


def select_gameplay(gameplay: Optional[str] = None) -> Path:
    """
    Pick the background clip for the split layout.

    ``gameplay`` may be an explicit path, a filename inside video/, or "random".
    """
    root = config.GAMEPLAY_DIR
    if gameplay and gameplay.lower() != "random":
        candidate = Path(gameplay)
        if not candidate.is_file():
            candidate = root / gameplay
        if not candidate.is_file():
            raise FileNotFoundError(
                f"Gameplay clip not found: {gameplay}. Looked in {root}."
            )
        return candidate

    videos = discover_gameplay_videos(root)
    if not videos:
        raise FileNotFoundError(
            f"No background clips found in {root}. Add an .mp4 to use the split layout."
        )
    return random.choice(videos)


def discover_photo_sets(photo_root: Optional[Path] = None) -> "dict[str, List[Path]]":
    """Return {folder_name: [sorted image paths]} for every subfolder of photo/."""
    photo_root = photo_root or (Path(__file__).parent / "photo")
    sets: "dict[str, List[Path]]" = {}
    if not photo_root.is_dir():
        return sets
    for folder in sorted(photo_root.iterdir()):
        if not folder.is_dir():
            continue
        images = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
        )
        if images:
            sets[folder.name] = images
    return sets


def select_photo_set(photo_set: Optional[str] = None) -> Tuple[Path, List[Path]]:
    """
    Pick one storyboard folder and return (folder, sorted images).

    Each folder is a different character pairing (photo/01 is man + man,
    photo/02 is man + woman), so by default a single folder is chosen at random
    per run to keep the two characters consistent across the whole reel.
    Pass ``photo_set`` (e.g. "01", "02") to force a specific folder.
    """
    photo_root = Path(__file__).parent / "photo"
    sets = discover_photo_sets(photo_root)
    if not sets:
        raise FileNotFoundError(f"No storyboard images found under {photo_root}")

    if photo_set and photo_set.lower() != "random":
        if photo_set not in sets:
            raise ValueError(
                f"Unknown photo set '{photo_set}'. Available: {', '.join(sorted(sets))}"
            )
        chosen = photo_set
    else:
        chosen = random.choice(sorted(sets))

    return photo_root / chosen, sets[chosen]


IdeaService = _load("01_ideas.idea_service", "IdeaService")
SupabaseIdeaStore = _load("01_ideas.supabase_store", "SupabaseIdeaStore")
ScriptService = _load("02_script.script_service", "ScriptService")
TTSService = _load("03_tts.audio_service", "TTSService")
AudioProcessor = _load("03_tts.audio_service", "AudioProcessor")
ImageManager = _load("04_images.image_service", "ImageManager")
CoverGenerator = _load("04_images.cover", "CoverGenerator")
build_character_panel = _load("04_images.panel", "build_character_panel")
fit_cover = _load("04_images.panel", "fit_cover")
stack_vertical = _load("04_images.panel", "stack_vertical")
SubtitleService = _load("05_captions.subtitle_service", "SubtitleService")
VideoRenderer = _load("06_video.video_service", "VideoRenderer")
CaptionService = _load("07_publish.caption", "CaptionService")
publish_reel_pipeline = _load("07_publish.instagram", "publish_reel_pipeline")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ReelPipeline")


def run_pipeline(
    topic: str = "Git vs GitHub",
    voice_a: str = config.DEFAULT_VOICE_A,
    voice_b: str = config.DEFAULT_VOICE_B,
    aspect_ratio: str = "9:16",
    job_id: Optional[str] = None,
    photo_set: Optional[str] = None,
    idea: Optional[dict] = None,
    layout: Optional[str] = None,
    gameplay: Optional[str] = None,
    publish: bool = True,
):
    layout = (layout or config.LAYOUT or "full").strip().lower()
    workflow = WorkflowManager(job_id=job_id)
    print(f"\n🚀 Starting Two-Person Reel Workflow (Job ID: {workflow.job_id})")
    print(f"📌 Topic: {topic} | Aspect Ratio: {aspect_ratio} | Layout: {layout}\n")

    if not voice_a or not voice_b:
        raise ValueError(
            "Missing ElevenLabs voice IDs. Set DEFAULT_VOICE_A and DEFAULT_VOICE_B in reel/.env."
        )

    # Step 1: Default Character Images
    char_a_path = config.ASSETS_DIR / "char_a.png"
    char_b_path = config.ASSETS_DIR / "char_b.png"
    if not char_a_path.exists():
        print("🎨 Generating Character A placeholder image...")
        ImageManager.create_default_avatar("Alex (Character A)", (41, 128, 185), "pocket", char_a_path)
    if not char_b_path.exists():
        print("🎨 Generating Character B placeholder image...")
        ImageManager.create_default_avatar("Sam (Character B)", (39, 174, 96), "thinking", char_b_path)

    # Step 2: Pick an idea (either supplied, e.g. from Supabase, or freshly generated).
    workflow.update_status("GENERATING_IDEAS")
    if idea:
        selected_idea = idea
        topic = selected_idea.get("topic") or selected_idea.get("title", topic)
        workflow.state["idea"] = selected_idea
        print(f"💡 Step 1: Using supplied idea: '{selected_idea.get('title', '')}'")
    else:
        print("💡 Step 1: Generating topic ideas via Gemini...")
        idea_svc = IdeaService()
        ideas = idea_svc.generate_ideas(topic=topic, count=3)
        selected_idea = ideas[0]
        workflow.state["idea"] = selected_idea
        print(f"   ✓ Selected Idea: '{selected_idea['title']}'")

        # Record every generated idea in Supabase (video_generated stays false).
        try:
            store = SupabaseIdeaStore()
            if store.is_configured:
                saved = store.save_ideas(ideas, topic=topic, tone="")
                workflow.state["saved_ideas"] = len(saved)
                print(f"   ✓ Recorded {len(saved)} idea(s) in Supabase table '{store.table}'")
        except Exception:
            logger.exception("Could not record ideas in Supabase (continuing).")

    # Step 3: Script Generation
    workflow.update_status("GENERATING_SCRIPT")
    print("\n📝 Step 2: Writing 2-person script...")
    script_svc = ScriptService()
    idea_summary = selected_idea.get("summary") or selected_idea.get("hook") or ""
    script = script_svc.generate_script(selected_idea["title"], idea_summary)
    workflow.state["script"] = script
    print(f"   ✓ Generated dialogue lines: {len(script['dialogue'])}")
    for line in script['dialogue']:
        spk = "Alex" if line['speaker'] == "character_a" else "Sam"
        print(f"     • [{spk}]: {line['text']}")

    # Step 4: Text-to-Speech Generation
    workflow.update_status("GENERATING_AUDIO")
    print("\n🎙️ Step 3: Synthesizing character voices via ElevenLabs...")
    tts = TTSService()
    line_files = []

    for idx, item in enumerate(script['dialogue']):
        spk = item['speaker']
        voice = voice_a if spk == "character_a" else voice_b
        out_line_path = workflow.job_dir / f"line_{idx:02d}_{spk}.mp3"
        print(f"   • Synthesizing line {idx+1}/{len(script['dialogue'])} using {voice}...")
        dur = tts.synthesize_line(item['text'], voice, out_line_path)
        line_files.append((out_line_path, dur))

    # Combine audio. A leading silence window (intro_sec) leaves room for the
    # cover image as the first frame; all timings are shifted by it so captions
    # stay in sync.
    final_audio_path = workflow.job_dir / "full_dialogue.mp3"
    intro_sec = max(config.COVER_INTRO_SEC, 0.0)
    print("   • Concatenating dialogue track with pauses...")
    timings = AudioProcessor.stitch_dialogue_audio(
        line_files, final_audio_path, pause_between_sec=0.3, intro_sec=intro_sec
    )
    workflow.state["audio_path"] = str(final_audio_path)

    # Step 5: Subtitle Generation
    workflow.update_status("PREPARING_SUBTITLES")
    print("\n💬 Step 4: Generating ASS and SRT subtitles...")
    sub_svc = SubtitleService()
    ass_path = workflow.job_dir / "subtitles.ass"
    srt_path = workflow.job_dir / "subtitles.srt"
    sub_svc.generate_ass(script['dialogue'], timings, ass_path)
    sub_svc.generate_srt(script['dialogue'], timings, srt_path)
    workflow.state["ass_path"] = str(ass_path)
    workflow.state["srt_path"] = str(srt_path)
    print("   • Subtitle timing maps generated.")

    # Step 6: Render Video via FFmpeg
    workflow.update_status("RENDERING_VIDEO")
    print("\n🎬 Step 5: Rendering final MP4 video via FFmpeg...")
    # A single photo set is chosen (randomly unless photo_set is given) and its
    # images are cycled one per line.
    image_dir, image_files = select_photo_set(photo_set)
    workflow.state["photo_set"] = image_dir.name
    workflow.state["layout"] = layout
    print(f"   • Using storyboard set '{image_dir.name}' ({len(image_files)} images)")

    renderer = VideoRenderer(aspect_ratio=aspect_ratio)
    total_duration = timings[-1]["end"] if timings else max(intro_sec, 0.1)
    title = selected_idea.get("title", "")
    hook = selected_idea.get("hook", "")
    title_hook = hook.strip() if (hook and hook.strip()) else title
    cover_path = workflow.job_dir / "cover.jpg"

    # Build the still source for each line, the cover, and the segment frame size.
    # "full" fills the whole frame with a storyboard image. "split" puts the
    # characters (cropped to their content) in a white top panel and a looping
    # gameplay clip in the bottom panel.
    if layout == "split":
        top_h = int(renderer.height * config.SPLIT_TOP_RATIO)
        top_h -= top_h % 2
        bottom_h = renderer.height - top_h
        gameplay_path = select_gameplay(gameplay)
        print(
            f"   • Split layout: characters {renderer.width}x{top_h} on top, "
            f"'{gameplay_path.name}' {renderer.width}x{bottom_h} below"
        )

        panel_cache: "dict[Path, Path]" = {}

        def panel_for(img: Path) -> Path:
            """Render (and cache) the character panel for one storyboard image."""
            if img not in panel_cache:
                panel_file = workflow.job_dir / f"panel_{img.stem}.png"
                build_character_panel(
                    img, renderer.width, top_h, title=title_hook
                ).save(panel_file)
                panel_cache[img] = panel_file
            return panel_cache[img]

        def line_still(_idx: int, img: Path) -> Path:
            return panel_for(img)

        # Cover: the first character panel stacked on a frame grabbed from the
        # gameplay clip. Used as the reel's first frame and its Instagram cover.
        # The reel title is drawn in the vertical centre of the thumbnail.
        print(f"   • Building split cover thumbnail with title centred: '{title}'...")
        gameplay_frame = workflow.job_dir / "gameplay_cover.jpg"
        subprocess.run([
            "ffmpeg", "-y", "-ss", "3", "-i", str(gameplay_path),
            "-frames:v", "1", str(gameplay_frame),
        ], check=True)
        stack_vertical(
            build_character_panel(image_files[0], renderer.width, top_h, title=None),
            fit_cover(gameplay_frame, (renderer.width, bottom_h)),
            cover_path,
            title=title,
        )

        segment_w, segment_h = renderer.width, top_h
        # The reel's first frame is the full cover, so the thumbnail preview
        # shows the title centred in the middle of the frame.
        intro_still = cover_path
    else:
        # Build the cover from the first storyboard image with the title centred.
        print(f"   • Building cover thumbnail with title centred: '{title}'...")
        CoverGenerator.create_cover(
            base_image=image_files[0],
            title=title,
            output_path=cover_path,
            width=renderer.width,
            height=renderer.height,
        )

        def line_still(_idx: int, img: Path) -> Path:
            return img

        segment_w, segment_h = renderer.width, renderer.height
        intro_still = cover_path

    # Render the stills as video segments and concatenate them (video only).
    segment_paths = []
    if intro_sec > 0 and layout != "split":
        # Static cover segment covering [0, intro_sec). The first dialogue line
        # starts exactly at intro_sec, so this fills the lead-in window. The
        # split layout handles its full-frame cover intro in the final pass.
        intro_path = workflow.job_dir / "segment_intro.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(intro_still),
            "-t", f"{intro_sec:.3f}",
            "-vf", f"scale={segment_w}:{segment_h}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(intro_path),
        ], check=True)
        segment_paths.append(intro_path)

    for idx, timing in enumerate(timings):
        # Each segment runs from this line's start to the next line's start, so it
        # absorbs the inter-line pause. Otherwise the pauses vanish from the video
        # timeline and every later line drifts out of sync with the audio.
        seg_start = timing["start"]
        seg_end = timings[idx + 1]["start"] if idx + 1 < len(timings) else timing["end"]
        seg_dur = max(seg_end - seg_start, 0.05)
        still = line_still(idx, image_files[idx % len(image_files)])
        segment_path = workflow.job_dir / f"segment_{idx:02d}.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(still),
            "-t", f"{seg_dur:.3f}",
            "-vf", f"scale={segment_w}:{segment_h}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(segment_path),
        ], check=True)
        segment_paths.append(segment_path)

    concat_list_path = workflow.job_dir / "concat_list.txt"
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for seg in segment_paths:
            f.write(f"file '{seg.resolve()}'\n")
    combined_path = workflow.job_dir / "combined_no_subs.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list_path), "-c", "copy", str(combined_path),
    ], check=True)

    final_video = workflow.job_dir / "final_video.mp4"
    if layout == "split":
        # Loop the gameplay clip under the character track, stack them, burn the
        # subtitles and mux the full dialogue audio in a single pass.
        clean_ass = (
            str(ass_path.resolve())
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
        )
        gameplay_start = round(random.uniform(0, 60), 2)
        # Duration of the character track (everything after the cover intro).
        body_dur = max(total_duration - intro_sec, 0.1)
        stack_chain = (
            f"[0:v]scale={renderer.width}:{top_h},setsar=1,fps=30[top];"
            f"[1:v]scale={renderer.width}:{bottom_h}:force_original_aspect_ratio=increase,"
            f"crop={renderer.width}:{bottom_h},setsar=1,fps=30,"
            f"trim=duration={body_dur:.3f},setpts=PTS-STARTPTS[bot];"
            f"[top][bot]vstack=inputs=2[vbody]"
        )
        if intro_sec > 0:
            # Prepend the full-frame cover (title centred) so the reel's first
            # frame, and therefore its thumbnail, matches the cover.
            filter_complex = (
                f"{stack_chain};"
                f"[3:v]scale={renderer.width}:{renderer.height},setsar=1,fps=30,"
                f"trim=duration={intro_sec:.3f},setpts=PTS-STARTPTS[intro];"
                f"[intro][vbody]concat=n=2:v=1:a=0[vcat];"
                f"[vcat]subtitles=filename='{clean_ass}'[vfinal]"
            )
            inputs = [
                "-i", str(combined_path),
                "-stream_loop", "-1", "-ss", f"{gameplay_start}", "-i", str(gameplay_path),
                "-i", str(final_audio_path),
                "-loop", "1", "-t", f"{intro_sec:.3f}", "-i", str(cover_path),
            ]
        else:
            filter_complex = (
                f"{stack_chain};"
                f"[vbody]subtitles=filename='{clean_ass}'[vfinal]"
            )
            inputs = [
                "-i", str(combined_path),
                "-stream_loop", "-1", "-ss", f"{gameplay_start}", "-i", str(gameplay_path),
                "-i", str(final_audio_path),
            ]
        subprocess.run([
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[vfinal]", "-map", "2:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(final_video),
        ], check=True)
    else:
        # Burn subtitles and mux the complete audio track in one pass. Using the
        # full dialogue file (instead of per-segment audio cuts) keeps the audio
        # perfectly aligned with the subtitle timings.
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(combined_path),
            "-i", str(final_audio_path),
            "-filter_complex", f"[0:v]subtitles='{ass_path.resolve()}'[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(final_video),
        ], check=True)

    workflow.state["video_path"] = str(final_video)

    workflow.update_status("COMPLETED")

    print("\n" + "="*50)
    print("🎉 SUCCESS! Video rendering completed.")
    print(f"📹 Final Video Path: {final_video.resolve()}")
    print(f"🎵 Audio Track Path: {final_audio_path.resolve()}")
    print(f"📄 SRT Subtitles Path: {srt_path.resolve()}")
    print(f"🖼️  Cover Image Path: {cover_path.resolve()}")
    print("="*50 + "\n")

    if not publish:
        print("⏭️  Publish skipped (publish disabled).")
        return workflow.state

    # -------------------------------------------------
    # Upload to storage and publish to Instagram
    # -------------------------------------------------
    try:
        try:
            print("✍️ Generating Instagram caption and hashtags...")
            caption = CaptionService().generate_caption(
                selected_idea["title"], selected_idea.get("summary", "")
            )
        except Exception:
            logger.exception("Caption generation failed; using fallback caption.")
            caption = CaptionService.fallback_caption(selected_idea["title"])
        workflow.state["caption"] = caption
        print(f"   ✓ Caption: {caption[:140]}")

        # publish_reel_pipeline uploads the video to storage and posts it, so we
        # must not upload it separately here (that would store it twice).
        publish_result = asyncio.run(publish_reel_pipeline(
            video_path=str(final_video),
            caption=caption,
            job_id=workflow.job_id,
            cover_path=str(cover_path) if cover_path.exists() else None,
        ))
        workflow.state["publish_result"] = publish_result
        logger.info(f"📱 Instagram publish result: {publish_result}")
    except Exception:
        logger.exception("⚠️ Upload or Instagram posting failed")

    return workflow.state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Two-Person Conversation Video Generator")
    parser.add_argument("--topic", type=str, default="Git vs GitHub", help="Topic for the video reel")
    parser.add_argument("--ratio", type=str, default="9:16", choices=["9:16", "16:9", "1:1"], help="Video aspect ratio")
    parser.add_argument(
        "--photo-set",
        type=str,
        default="random",
        help="Storyboard folder under photo/ to use (e.g. 01, 02) or 'random' to pick one per run",
    )
    parser.add_argument(
        "--layout",
        type=str,
        default=None,
        choices=["full", "split"],
        help="full = one storyboard image filling the frame; split = characters on top, gameplay clip below",
    )
    parser.add_argument(
        "--gameplay",
        type=str,
        default="random",
        help="Background clip for the split layout: a path, a filename in video/, or 'random'",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Render the video locally without posting it to Instagram",
    )
    args = parser.parse_args()

    try:
        run_pipeline(
            topic=args.topic,
            aspect_ratio=args.ratio,
            photo_set=args.photo_set,
            layout=args.layout,
            gameplay=args.gameplay,
            publish=not args.no_publish,
        )
    except Exception:
        logger.exception("❌ Pipeline failed.")
        sys.exit(1)

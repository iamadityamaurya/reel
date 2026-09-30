#!/usr/bin/env python3
"""
CLI & Modular Orchestrator for AI Two-Person Conversation Video Generator
Run this script end-to-end to generate complete conversational reels!
"""

import sys
import argparse
import logging
import asyncio
import importlib
import subprocess
from pathlib import Path
from typing import Optional

import config
from workflow_manager import WorkflowManager


def _load(module_path: str, name: str):
    """Import a numbered stage package (e.g. "01_ideas.idea_service")."""
    return getattr(importlib.import_module(module_path), name)


IdeaService = _load("01_ideas.idea_service", "IdeaService")
ScriptService = _load("02_script.script_service", "ScriptService")
TTSService = _load("03_tts.audio_service", "TTSService")
AudioProcessor = _load("03_tts.audio_service", "AudioProcessor")
ImageManager = _load("04_images.image_service", "ImageManager")
SubtitleService = _load("05_captions.subtitle_service", "SubtitleService")
VideoRenderer = _load("06_video.video_service", "VideoRenderer")
publish_reel_pipeline = _load("07_publish.instagram", "publish_reel_pipeline")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ReelPipeline")

def run_pipeline(
    topic: str = "Git vs GitHub",
    voice_a: str = config.DEFAULT_VOICE_A,
    voice_b: str = config.DEFAULT_VOICE_B,
    aspect_ratio: str = "9:16",
    job_id: Optional[str] = None
):
    workflow = WorkflowManager(job_id=job_id)
    print(f"\n🚀 Starting Two-Person Reel Workflow (Job ID: {workflow.job_id})")
    print(f"📌 Topic: {topic} | Aspect Ratio: {aspect_ratio}\n")

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

    # Step 2: Generate Ideas
    workflow.update_status("GENERATING_IDEAS")
    print("💡 Step 1: Generating topic ideas via Groq...")
    idea_svc = IdeaService()
    ideas = idea_svc.generate_ideas(topic=topic, count=3)
    selected_idea = ideas[0]
    workflow.state["idea"] = selected_idea
    print(f"   ✓ Selected Idea: '{selected_idea['title']}'")

    # Step 3: Script Generation
    workflow.update_status("GENERATING_SCRIPT")
    print("\n📝 Step 2: Writing 2-person script...")
    script_svc = ScriptService()
    script = script_svc.generate_script(selected_idea["title"], selected_idea["summary"])
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

    # Combine audio
    final_audio_path = workflow.job_dir / "full_dialogue.mp3"
    print("   • Concatenating dialogue track with pauses...")
    timings = AudioProcessor.stitch_dialogue_audio(line_files, final_audio_path, pause_between_sec=0.3)
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
    print("   ✓ Subtitle timing maps generated.")

    # Step 6: Render Video via FFmpeg
    workflow.update_status("RENDERING_VIDEO")
    print("\n🎬 Step 5: Rendering final MP4 video via FFmpeg...")
    # Render storyboard video using per-line images
    image_dir = Path(__file__).parent / "photo" / "01"
    image_files = sorted([p for p in image_dir.glob("*.jpg")])
    if not image_files:
        raise FileNotFoundError("Storyboard images not found in photo/01")
    
    # Initialize renderer for dimensions
    renderer = VideoRenderer(aspect_ratio=aspect_ratio)
    segment_paths = []
    for idx, timing in enumerate(timings):
        # Each segment runs from this line's start to the next line's start, so it
        # absorbs the inter-line pause. Otherwise the pauses vanish from the video
        # timeline and every later line drifts out of sync with the audio.
        seg_start = timing["start"]
        seg_end = timings[idx + 1]["start"] if idx + 1 < len(timings) else timing["end"]
        seg_dur = max(seg_end - seg_start, 0.05)
        img_path = image_files[idx % len(image_files)]
        segment_path = workflow.job_dir / f"segment_{idx:02d}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_path),
            "-t", f"{seg_dur:.3f}",
            "-vf", f"scale={renderer.width}:{renderer.height}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(segment_path)
        ]
        subprocess.run(cmd, check=True)
        segment_paths.append(segment_path)
    
    # Concatenate segment videos (video-only, no audio yet)
    concat_list_path = workflow.job_dir / "concat_list.txt"
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for seg in segment_paths:
            f.write(f"file '{seg.resolve()}'\n")
    combined_path = workflow.job_dir / "combined_no_subs.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list_path), "-c", "copy", str(combined_path)
    ], check=True)
    
    # Burn subtitles and mux the complete audio track in one pass. Using the full
    # dialogue file (instead of per-segment audio cuts) keeps the audio perfectly
    # aligned with the subtitle timings.
    final_video = workflow.job_dir / "final_video.mp4"
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
        str(final_video)
    ], check=True)
    
    workflow.state["video_path"] = str(final_video)
    

    workflow.update_status("COMPLETED")

    print("\n" + "="*50)
    print("🎉 SUCCESS! Video rendering completed.")
    print(f"📹 Final Video Path: {final_video.resolve()}")
    print(f"🎵 Audio Track Path: {final_audio_path.resolve()}")
    print(f"📄 SRT Subtitles Path: {srt_path.resolve()}")
    print("="*50 + "\n")

    # -------------------------------------------------
    # Upload to storage and publish to Instagram
    # -------------------------------------------------
    try:
        caption = f"New Reel: {topic} - generated with AI 🎬"

        # publish_reel_pipeline uploads the video to storage and posts it, so we
        # must not upload it separately here (that would store it twice).
        publish_result = asyncio.run(publish_reel_pipeline(
            video_path=str(final_video),
            caption=caption,
            job_id=workflow.job_id,
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
    args = parser.parse_args()

    try:
        run_pipeline(topic=args.topic, aspect_ratio=args.ratio)
    except Exception:
        logger.exception("❌ Pipeline failed.")
        sys.exit(1)

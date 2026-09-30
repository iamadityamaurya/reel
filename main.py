#!/usr/bin/env python3
"""
CLI & Modular Orchestrator for AI Two-Person Conversation Video Generator
Run this script end-to-end to generate complete conversational reels!
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

import config
from dotenv import load_dotenv
load_dotenv('/home/aditys/code/education/.env')
import os
import boto3
import requests
import subprocess
from idea_service import IdeaService
from script_service import ScriptService
from audio_service import TTSService, AudioProcessor
from subtitle_service import SubtitleService
from video_service import ImageManager, VideoRenderer
from workflow_manager import WorkflowManager

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
    print("\n🎙️ Step 3: Synthesizing character voices via Deepgram...")
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
    from pathlib import Path
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
    # Upload to Supabase and post to Instagram
    # -------------------------------------------------
    try:
        # Use shared utilities from the education project for storage upload and
        # Instagram publishing. Import them as a package (the way the education
        # project does) so their relative imports resolve. Adding the 07_publish
        # folder directly to sys.path would break `from .storage import ...`.
        import importlib
        education_root = Path('/home/aditys/code/education')
        if str(education_root) not in sys.path:
            sys.path.insert(0, str(education_root))
        publish_module = importlib.import_module('07_publish.instagram')
        upload_file = publish_module.upload_file
        publish_reel_pipeline = publish_module.publish_reel_pipeline
        import asyncio

        # Upload video to storage and get public URL
        video_filename = final_video.name
        public_url = upload_file(str(final_video), object_name=video_filename)
        logger.info(f"📤 Uploaded to storage: {public_url}")

        # Prepare caption
        caption = f"New Reel: {topic} – generated with AI 🎬"

        # Publish to Instagram
        publish_result = asyncio.run(publish_reel_pipeline(
            video_path=str(final_video),
            caption=caption,
            job_id=workflow.job_id,
        ))
        logger.info(f"📱 Instagram publish result: {publish_result}")
    except Exception as e:
        logger.error(f"⚠️ Upload or Instagram posting failed: {e}")

    return workflow.state

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Two-Person Conversation Video Generator")
    parser.add_argument("--topic", type=str, default="Git vs GitHub", help="Topic for the video reel")
    parser.add_argument("--ratio", type=str, default="9:16", choices=["9:16", "16:9", "1:1"], help="Video aspect ratio")
    args = parser.parse_args()

    run_pipeline(topic=args.topic, aspect_ratio=args.ratio)

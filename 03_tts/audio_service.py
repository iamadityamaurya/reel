import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple

from elevenlabs.client import ElevenLabs

import config
from utils import retry_call

logger = logging.getLogger(__name__)

class TTSService:
    def __init__(self):
        if not config.ELEVENLABS_API_KEY:
            raise ValueError(
                "ELEVENLABS_API_KEY is not set. Add it to reel/.env to generate audio."
            )
        self.client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY, timeout=120.0)

    def synthesize_line(self, text: str, voice_name: str, output_path: Path) -> float:
        """Synthesizes a single dialogue line using ElevenLabs."""
        if not voice_name:
            raise ValueError(
                "Missing ElevenLabs voice ID. Set DEFAULT_VOICE_A / DEFAULT_VOICE_B in reel/.env."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Consume the stream inside the retry so transient network errors are retried.
        chunks = retry_call(
            lambda: list(self.client.text_to_speech.convert(
                text=text,
                voice_id=voice_name,
                model_id=config.ELEVENLABS_MODEL_ID,
            )),
            attempts=3,
            base_delay=2.0,
            description=f"ElevenLabs TTS for '{text[:40]}...'",
        )

        with open(output_path, "wb") as f:
            for chunk in chunks:
                f.write(chunk)

        duration = self.get_audio_duration(output_path)
        return duration

    @staticmethod
    def get_audio_duration(audio_path: Path) -> float:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            return float(res.stdout.strip())
        except Exception:
            return 2.5

class AudioProcessor:
    @staticmethod
    def stitch_dialogue_audio(
        line_files: List[Tuple[Path, float]], 
        output_concat_path: Path, 
        pause_between_sec: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Combines individual audio files into a single continuous track with padding.
        Returns precise start and end timing data for each dialogue line for subtitles.
        """
        output_concat_path.parent.mkdir(parents=True, exist_ok=True)

        # Compute subtitle timings and the ordered list of audio segments.
        # The pauses are part of the timeline, so each line's end leaves room for
        # the pause before the next line's start.
        timings = []
        current_time = 0.0
        for idx, (file_path, duration) in enumerate(line_files):
            start_t = current_time
            end_t = current_time + duration
            timings.append({
                "line_index": idx,
                "start": start_t,
                "end": end_t,
                "duration": duration
            })
            current_time = end_t
            if pause_between_sec > 0 and idx < len(line_files) - 1:
                current_time += pause_between_sec

        if not line_files:
            raise ValueError("No audio lines to stitch")

        silence_file = output_concat_path.parent / "silence.wav"
        if pause_between_sec > 0:
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo",
                "-t", str(pause_between_sec),
                str(silence_file)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        segments: List[Path] = []
        for idx, (file_path, _) in enumerate(line_files):
            segments.append(Path(file_path))
            if pause_between_sec > 0 and idx < len(line_files) - 1:
                segments.append(silence_file)

        # Use the concat *filter* with every input normalised to the same PCM
        # format. The concat demuxer cannot mix differently-formatted inputs
        # (e.g. mono MP3 + stereo WAV): it silently drops the mismatched segments,
        # which removed all the pauses and desynced the subtitles by ~0.3s/line.
        cmd = ["ffmpeg", "-y"]
        for seg in segments:
            cmd += ["-i", str(seg)]

        n = len(segments)
        normalise = ";".join(
            f"[{i}:a]aresample=44100,aformat=sample_fmts=s16:channel_layouts=stereo[a{i}]"
            for i in range(n)
        )
        concat = "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[outa]"
        cmd += [
            "-filter_complex", f"{normalise};{concat}",
            "-map", "[outa]",
            "-c:a", "libmp3lame", "-q:a", "2",
            str(output_concat_path)
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg audio concat failed: {res.stderr}")

        return timings

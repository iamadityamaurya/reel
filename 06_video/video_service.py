"""Video rendering (side-by-side characters with burned-in ASS subtitles)."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VideoRenderer:
    def __init__(self, aspect_ratio: str = "9:16"):
        self.aspect_ratio = aspect_ratio
        if aspect_ratio == "9:16":
            self.width, self.height = 1080, 1920
        elif aspect_ratio == "16:9":
            self.width, self.height = 1920, 1080
        else: # 1:1
            self.width, self.height = 1080, 1080

    def render_video(
        self,
        char_a_img: Path,
        char_b_img: Path,
        audio_path: Path,
        ass_subtitle_path: Optional[Path],
        output_mp4_path: Path,
        bg_color: str = "white"
    ) -> Path:
        """
        Renders side-by-side 2-character video with audio track and burned-in ASS subtitles via FFmpeg.
        """
        output_mp4_path.parent.mkdir(parents=True, exist_ok=True)

        # Prepare layout filter
        # Canvas size: width x height
        # Character A on Left, Character B on Right
        # Scale characters to fit within half frame height nicely
        char_w = int(self.width * 0.42)
        char_h = int(self.height * 0.55)

        pos_a_x = int(self.width * 0.06)
        pos_a_y = int(self.height * 0.40)

        pos_b_x = int(self.width * 0.52)
        pos_b_y = int(self.height * 0.40)

        # Build FFmpeg command with complex filter graph
        filter_graph = [
            f"color=c={bg_color}:s={self.width}x{self.height}:r=30[bg]",
            f"[0:v]scale={char_w}:{char_h}:force_original_aspect_ratio=decrease[charA]",
            f"[1:v]scale={char_w}:{char_h}:force_original_aspect_ratio=decrease[charB]",
            f"[bg][charA]overlay=x={pos_a_x}:y={pos_a_y}[tmp1]",
            f"[tmp1][charB]overlay=x={pos_b_x}:y={pos_b_y}[vbase]"
        ]

        if ass_subtitle_path and ass_subtitle_path.exists():
            clean_ass_path = str(ass_subtitle_path.resolve()).replace(":", "\\:").replace("'", "\\'")
            filter_graph.append(f"[vbase]subtitles=filename='{clean_ass_path}'[vfinal]")
            final_v_label = "[vfinal]"
        else:
            final_v_label = "[vbase]"

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(char_a_img.resolve()),
            "-loop", "1", "-i", str(char_b_img.resolve()),
            "-i", str(audio_path.resolve()),
            "-filter_complex", ";".join(filter_graph),
            "-map", final_v_label,
            "-map", "2:a",
            "-c:v", "libx264", "-tune", "stillimage", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-pix_fmt", "yuv420p",
            str(output_mp4_path)
        ]

        logger.info("Executing FFmpeg Video Render...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg rendering failed: {res.stderr}")

        return output_mp4_path

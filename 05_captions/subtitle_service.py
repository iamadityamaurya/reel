import math
import re
from pathlib import Path
from typing import List, Dict, Any

class SubtitleService:
    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """Converts float seconds to ASS format h:mm:ss.cs (centiseconds)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centis = int(round((seconds - int(seconds)) * 100))
        if centis >= 100:
            secs += 1
            centis -= 100
        return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

    @staticmethod
    def format_srt_timestamp(seconds: float) -> str:
        """Converts float seconds to SRT format hh:mm:ss,mss."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000))
        if millis >= 1000:
            secs += 1
            millis -= 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def chunk_words(self, text: str, words_per_chunk: int = 3) -> List[str]:
        """Splits full sentence text into short 2-4 word animated chunks."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), words_per_chunk):
            chunks.append(" ".join(words[i:i + words_per_chunk]))
        return chunks

    def generate_ass(
        self,
        dialogue: List[Dict[str, Any]],
        timings: List[Dict[str, Any]],
        output_ass_path: Path,
        font_size: int = 68,
        margin_v: int = 220
    ) -> Path:
        """
        Generates modern Instagram Reel dynamic animated ASS subtitles:
        - Big bold white font with black outline & shadow.
        - Word-chunked short phrases (3 words per popup).
        - The last word of each chunk is highlighted in the speaker's colour:
          Alex is yellow, Sam is cyan, so viewers can tell who is talking.
        - Positioned cleanly in lower third of 9:16 canvas (`PlayRes: 1080x1920`).
        """
        header = f"""[Script Info]
Title: Dynamic Reel Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: AlexStyle, Liberation Sans,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,6,3,2,60,60,{margin_v},1
Style: SamStyle, Liberation Sans,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,6,3,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        # ASS colours are &HAABBGGRR. Yellow = &H00FFFF, cyan = &HFFFF00.
        speaker_styles = {
            "character_a": (r"{\c&H00FFFF&}", "AlexStyle"),
            "character_b": (r"{\c&HFFFF00&}", "SamStyle"),
        }
        white_start = r"{\c&HFFFFFF&}"

        for d, t in zip(dialogue, timings):
            highlight_start, style_name = speaker_styles.get(
                d.get("speaker"), speaker_styles["character_a"]
            )
            line_start = t["start"]
            line_end = t["end"]
            line_duration = t["duration"]
            raw_text = d.get("text", "").strip()

            chunks = self.chunk_words(raw_text, words_per_chunk=3)
            if not chunks:
                continue

            chunk_duration = line_duration / len(chunks)

            for idx, chunk in enumerate(chunks):
                c_start = line_start + (idx * chunk_duration)
                c_end = c_start + chunk_duration
                start_str = self.format_timestamp(c_start)
                end_str = self.format_timestamp(c_end)

                # Format chunk: highlight last word in the speaker's colour for a viral look
                words = chunk.split()
                if len(words) > 1:
                    normal_part = " ".join(words[:-1])
                    highlight_word = words[-1]
                    formatted_text = f"{normal_part} {highlight_start}{highlight_word}{white_start}"
                else:
                    formatted_text = f"{highlight_start}{chunk}{white_start}"

                events.append(f"Dialogue: 0,{start_str},{end_str},{style_name},,0,0,0,,{formatted_text}")

        output_ass_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")

        return output_ass_path

    def generate_srt(
        self,
        dialogue: List[Dict[str, Any]],
        timings: List[Dict[str, Any]],
        output_srt_path: Path
    ) -> Path:
        """Generates standard SRT subtitle file."""
        lines = []
        for idx, (d, t) in enumerate(zip(dialogue, timings), start=1):
            start_str = self.format_srt_timestamp(t["start"])
            end_str = self.format_srt_timestamp(t["end"])
            speaker_label = "Alex" if d.get("speaker") == "character_a" else "Sam"
            text = d.get("text", "")
            lines.append(f"{idx}\n{start_str} --> {end_str}\n{speaker_label}: {text}\n")

        output_srt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_srt_path

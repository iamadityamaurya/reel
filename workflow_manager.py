import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
import config

logger = logging.getLogger(__name__)

class WorkflowManager:
    def __init__(self, job_id: Optional[str] = None):
        self.job_id = job_id or str(uuid.uuid4())[:8]
        self.job_dir = config.JOBS_DIR / self.job_id
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.job_dir / "state.json"
        
        self.state: Dict[str, Any] = {
            "job_id": self.job_id,
            "status": "IDLE",
            "topic": "",
            "idea": None,
            "script": None,
            "char_a_img": str(config.ASSETS_DIR / "char_a.png"),
            "char_b_img": str(config.ASSETS_DIR / "char_b.png"),
            "voice_a": config.DEFAULT_VOICE_A,
            "voice_b": config.DEFAULT_VOICE_B,
            "aspect_ratio": "9:16",
            "audio_path": None,
            "srt_path": None,
            "ass_path": None,
            "video_path": None,
            "error": None
        }
        self.load_state()

    def save_state(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.state.update(json.load(f))
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

    def update_status(self, status: str, error: Optional[str] = None):
        self.state["status"] = status
        if error:
            self.state["error"] = error
        self.save_state()

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent

# Load this project's .env regardless of the current working directory.
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
JOBS_DIR = PROJECT_ROOT / "jobs"

for d in [DATA_DIR, ASSETS_DIR, JOBS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
DEFAULT_VOICE_A = os.getenv("DEFAULT_VOICE_A", "")
DEFAULT_VOICE_B = os.getenv("DEFAULT_VOICE_B", "")

# Cloud storage (Supabase S3 / AWS S3 / Cloudflare R2)
# Consumed by the local storage.py / instagram.py publishing modules.
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "mock")
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "")
STORAGE_PUBLIC_BASE_URL = os.getenv("STORAGE_PUBLIC_BASE_URL", "")
STORAGE_ACCESS_KEY = os.getenv("STORAGE_ACCESS_KEY", "")
STORAGE_SECRET_KEY = os.getenv("STORAGE_SECRET_KEY", "")
STORAGE_ENDPOINT_URL = os.getenv("STORAGE_ENDPOINT_URL", "")

# Instagram Graph API
IG_USER_ID = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")

# Execution mode - when True, publishing is simulated instead of hitting the API
DRY_RUN_MODE = os.getenv("DRY_RUN_MODE", "false").strip().lower() in ("1", "true", "yes")

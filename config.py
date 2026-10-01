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

# Idea generation uses Google Gemini. Groq is still used for the script + captions.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_BASE = os.getenv(
    "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
DEFAULT_VOICE_A = os.getenv("DEFAULT_VOICE_A", "")
DEFAULT_VOICE_B = os.getenv("DEFAULT_VOICE_B", "")

# Cover image is shown as the reel's first frame for this many seconds before the
# dialogue starts. Set to 0 to disable the cover intro.
COVER_INTRO_SEC = float(os.getenv("COVER_INTRO_SEC", "1.5"))

# Layout: "full" fills the whole frame with one storyboard image per line.
# "split" puts the two characters in the top part and a looping background clip
# (e.g. gameplay footage from the video/ folder) in the bottom part.
LAYOUT = os.getenv("LAYOUT", "full")
# Fraction of the 9:16 frame given to the character panel in the split layout.
SPLIT_TOP_RATIO = float(os.getenv("SPLIT_TOP_RATIO", "0.583"))
# Folder searched for background clips used by the split layout.
GAMEPLAY_DIR = PROJECT_ROOT / "video"

# Cloud storage (Supabase S3 / AWS S3 / Cloudflare R2)
# Consumed by the local storage.py / instagram.py publishing modules.
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "mock")
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "")
STORAGE_PUBLIC_BASE_URL = os.getenv("STORAGE_PUBLIC_BASE_URL", "")
STORAGE_ACCESS_KEY = os.getenv("STORAGE_ACCESS_KEY", "")
STORAGE_SECRET_KEY = os.getenv("STORAGE_SECRET_KEY", "")
STORAGE_ENDPOINT_URL = os.getenv("STORAGE_ENDPOINT_URL", "")

# Supabase (PostgREST) - optional record of every generated idea.
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_IDEAS_TABLE = os.getenv("SUPABASE_IDEAS_TABLE", "ideas")

# Instagram Graph API
IG_USER_ID = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")

# Execution mode - when True, publishing is simulated instead of hitting the API
DRY_RUN_MODE = os.getenv("DRY_RUN_MODE", "false").strip().lower() in ("1", "true", "yes")

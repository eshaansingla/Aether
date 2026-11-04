from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
PROJECT_DIR = BASE_DIR.parent
OUTPUT_DIR = Path(os.getenv("AETHER_OUTPUT_DIR", "output"))
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = (PROJECT_DIR / OUTPUT_DIR).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR = DATA_DIR / "notes"
NOTES_DIR.mkdir(exist_ok=True)
ALLOWED_ORIGIN = os.getenv("AETHER_ALLOWED_ORIGIN", "http://localhost:5173")
DB_PATH = BASE_DIR / "aether.db"
OLLAMA_BASE_URL = os.getenv("AETHER_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("AETHER_MODEL", "qwen3:1.7b")
OLLAMA_FAST_MODEL = os.getenv("AETHER_FAST_MODEL", OLLAMA_MODEL)
WHISPER_MODEL = os.getenv("AETHER_WHISPER_MODEL", "base")
BROWSER_PROFILE = DATA_DIR / "browser_profile"

from pathlib import Path
import os
from dotenv import load_dotenv

# Must be set before `transformers`/`huggingface_hub` is imported anywhere (app.eval.metrics
# does this lazily, on first local-model use) — their newer "xet" chunked-transfer download
# backend hung indefinitely in this environment (0% CPU, no progress, no error) downloading
# distilgpt2, where the classic HTTP downloader completed normally in a few seconds. This
# forces the classic path everywhere in the process, not just in one call site.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

BASE_DIR = Path(__file__).resolve().parents[1]
# override=True: this project's own .env is the intended source of truth for its config.
# Without it, python-dotenv silently keeps whatever's already in the process environment
# (e.g. a stray OPENAI_API_KEY set system-wide from something unrelated) instead of the
# key actually written here — which looks exactly like "the key is wrong" from outside.
load_dotenv(BASE_DIR / ".env", override=True)
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

# Three providers are supported, switchable with one setting (AETHER_PROVIDER): OpenAI,
# Groq, and Gemini. All three can share one code path because Groq's API is wire-compatible
# with OpenAI's format by design, and Google separately publishes an OpenAI-compatible
# endpoint for Gemini (https://ai.google.dev/gemini-api/docs/openai) — so "the OpenAI
# request/response shape" is really a lingua franca here, not something specific to OpenAI
# itself. Each provider keeps its own API key env var so switching back and forth never
# requires re-entering a key.
_PROVIDERS = {
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY", "default_model": "gpt-4o-mini"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY", "default_model": "openai/gpt-oss-120b"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "key_env": "GEMINI_API_KEY", "default_model": "gemini-3.8-flash"},
}
AI_PROVIDER = os.getenv("AETHER_PROVIDER", "groq").strip().lower()
_provider_cfg = _PROVIDERS.get(AI_PROVIDER, _PROVIDERS["groq"])
AI_API_KEY = os.getenv(_provider_cfg["key_env"], "")
AI_BASE_URL = os.getenv("AETHER_API_BASE_URL", _provider_cfg["base_url"]).rstrip("/")
AI_MODEL = os.getenv("AETHER_MODEL", _provider_cfg["default_model"])
AI_FAST_MODEL = os.getenv("AETHER_FAST_MODEL", AI_MODEL)
WHISPER_MODEL = os.getenv("AETHER_WHISPER_MODEL", "base")
BROWSER_PROFILE = DATA_DIR / "browser_profile"

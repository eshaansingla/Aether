# AI model setup (cloud API)

AETHER's language-model inference runs through a cloud API rather than a model bundled
with the app. Three providers are supported, selected with one setting:

```
# backend/.env
AETHER_PROVIDER=groq      # openai | groq | gemini
GROQ_API_KEY=...
```

Each provider keeps its own key in `.env` at the same time, so switching providers is a
one-line change (`AETHER_PROVIDER`) with no need to re-enter a key.

| Provider | Free tier? | Get a key |
|---|---|---|
| Groq | Yes, no card required | https://console.groq.com/keys |
| Google Gemini | Yes, no card required (use a standard `AIzaSy...` key, not an OAuth token) | https://aistudio.google.com/apikey |
| OpenAI | No - paid, billing must be funded | https://platform.openai.com/api-keys |

Groq and Gemini both expose an API that's wire-compatible with OpenAI's chat-completions
format, so the backend (`app/services/agent.py`) uses the same request/response code for
all three - only the base URL, key, and model name differ (`app/config.py`).

## Models

Leave `AETHER_MODEL` / `AETHER_FAST_MODEL` unset to use each provider's current default
(see `_PROVIDERS` in `app/config.py`), or set them to pin a specific model. Provider
catalogs change over time - if a model starts returning `404 Not Found`, check the
provider's current model list and update the default or your `.env`.

## What still runs locally

Speech-to-text (faster-whisper) and text-to-speech (the OS's speech engine) run entirely
on-device and need no API key. Only text generation (chat replies, document/code
generation, action classification) goes through the configured cloud provider.

## Sampling strategies (Playground + every chat/document reply)

Both the desktop app's Playground page and the main chat/document-writing flow run one
prompt through **6** sampling presets in parallel and let you pick which output to keep
(`app/services/agent.py` `SAMPLING_PRESETS` / `generate_variant_any`, `POST /api/compare`,
`POST /api/tasks/{id}/select`): greedy decoding (temperature=0), low-temperature sampling,
nucleus (top-p) sampling, and high-temperature random sampling, all via the live cloud
provider - plus **top-k sampling and beam search**, run for real on a small local model
(`distilgpt2` via Hugging Face Transformers' own `generate()`), since no hosted
chat-completions API exposes either. Confirmed directly against Groq: `top_k` → `400
"unsupported property"`; requesting more than one completion per call (`n>1`, which beam
search would need) → `400 "'n' must be at most 1"`. This is a provider-layer limitation
common to OpenAI/Groq/Gemini, not specific to this app - each cloud strategy genuinely
needs its own separate API call, and top-k/beam genuinely need their own local decode loop.

Every variant is scored with perplexity (and, when grounding context exists, a
grounding-truthfulness check and a BLEU/ROUGE-vs-source similarity score) - shown
directly on each card, both in the Playground and inline in the chat thread.

## Evaluation harness (BLEU / ROUGE / perplexity, aggregated per strategy)

`scripts/evaluate_generation.py` runs a fixed set of prompts through `POST /api/compare`
(all 6 strategies per prompt) and scores each with BLEU and ROUGE-L (against a reference
answer, where one meaningfully exists - factual QA and summarization, not open-ended
essays or poems) and perplexity (every case, every strategy). One-time setup:

```
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Then, with the backend running (`uvicorn app.main:app ...`):

```
cd backend
PYTHONPATH=. python scripts/evaluate_generation.py
```

Each run is saved as `eval_results/run_<timestamp>.json` (kept, not overwritten, so runs
stay comparable over time) and refreshes `eval_results/latest_summary.md` with a
per-strategy aggregate table - mean perplexity/BLEU/ROUGE-L across every test prompt,
grouped by sampling strategy, ready to paste into `docs/PROJECT_REPORT.md`.

Perplexity can't be computed from the live provider's own output probabilities - Groq's
API rejects the `logprobs` parameter outright (`400: logprobs is not supported with this
model`), and this is a general hosted-chat-completions-API limitation, not something
fixable in this codebase. Instead, `app/eval/metrics.py` scores the generated text with
a small, fixed, independent reference model (`distilgpt2`, loaded locally only for this
scoring step) - a standard technique in NLG evaluation for measuring how predictable/
fluent generated text is, decoupled from whichever provider actually generated it.

## Reproducibility note: provider catalogs change

Mid-build, Groq deprecated the model this project started on (`llama-3.3-70b-versatile`
→ `404 Not Found`) and Google deprecated `gemini-2.0-flash` the same way. This is a real,
ongoing risk for anyone re-running this project later: a free-tier provider's model
catalog is not a stable API contract. If `AETHER_MODEL`/`AETHER_FAST_MODEL` starts
404ing, it means the provider removed that model - check its current model list
(`GET {base_url}/models` with your key) and either update `app/config.py`'s `_PROVIDERS`
default or set `AETHER_MODEL` in `.env` to a current model name. This isn't a bug to
chase in this codebase; it's an inherent property of depending on a free hosted API, and
the fix is always "pick a current model name," never a code change.

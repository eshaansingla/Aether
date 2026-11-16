# AETHER — Desktop AI Assistant

AETHER is a Windows-first desktop assistant that routes natural-language commands to
controlled productivity tools. The assistant's own logic — action routing, tool
execution, file/notes/reminders handling, speech recognition — runs on your device.
Text generation (chat replies, document and code generation, action classification)
is produced by a pretrained large language model accessed through a cloud API; no
model weights are trained or run on-device for text generation.

Three interchangeable API providers are supported — OpenAI, Groq, or Google Gemini —
selected with one setting (see `backend/MODEL_SETUP.md`). Groq's free tier needs no
credit card and is the default.

## Features in this prototype
- ChatGPT-inspired Electron + React desktop chat UI, with Markdown rendering (tables,
  bold, headings, code blocks) for AI replies.
- LLM-based command understanding and document/code generation via a cloud AI API.
- Local task history in SQLite.
- Notes saved as Markdown.
- Reminders scheduled and displayed in the app.
- Allowlisted Windows app launching.
- Spotify search launch (internet/service account may be required).
- Filename search in Desktop, Documents and Downloads.
- DOCX/TXT/code-file document creation.
- Local speech-to-text using faster-whisper.
- Read-aloud using the operating system's available speech synthesis.
- Keyless factual grounding (DuckDuckGo instant-answer lookup) plus a self-verification
  pass that catches the model stating a specific fact its source material doesn't
  actually contain, instead of surfacing it as a confident wrong answer.
- Settings page showing live AI API connection status.
- Playground page: runs one prompt through 4 sampling strategies (greedy, low-temperature,
  nucleus/top-p, high-temperature) in parallel and shows all 4 outputs side by side.
- Offline evaluation harness (`backend/scripts/evaluate_generation.py`) scoring
  generation quality with BLEU, ROUGE-1/2/L, and perplexity.

## One-click setup (Windows 10/11)

1. Extract the ZIP to a normal folder, such as `C:\\AETHER`.
2. Get a free API key — Groq (no card needed): https://console.groq.com/keys.
3. Double-click `SETUP_AND_RUN.bat`. It installs missing Python 3.11/Node.js LTS
   (via winget), creates the Python environment, installs all project dependencies,
   and creates `backend/.env` from `backend/.env.example` if it doesn't exist yet.
4. Open `backend/.env`, set `AETHER_PROVIDER` (default `groq`) and paste your key into
   the matching `*_API_KEY` line, then rerun `SETUP_AND_RUN.bat` (or `START_AETHER.bat`).
5. For later launches, double-click `START_AETHER.bat`.

Internet access is required every time AETHER generates text (it calls the configured
cloud API) — this is different from earlier prototypes of this project, which ran a
local Ollama model entirely offline. See `backend/MODEL_SETUP.md` for provider details
and `backend/.env.example` for every setting.

The setup scripts are in `windows/`. The backend and desktop commands are prewritten;
you do not need to type them manually.

## Example commands
- `Play some relaxing music`
- `Take a note: Finish the project report`
- `Remind me to take a break in 20 minutes`
- `Open Calculator`
- `Find my resume`
- `Create a Word document about renewable energy`

## AI concepts
See `docs/PROJECT_REPORT.md` and `docs/ARCHITECTURE.md` for the full writeup. In short:
AETHER uses pretrained Transformer-family LLMs (served by OpenAI/Groq/Gemini) as a
black box — this project does not pretrain, fine-tune, or implement attention/MHA from
scratch. What it demonstrates instead is prompt engineering, structured action routing,
tool execution, grounding/fact-verification, and a basic agentic workflow built on top
of an API-served model.

### Alignment with Quiz-1 syllabus
Honest mapping of what's actually implemented against the course's Quiz-1 topics —
useful context for the report, and for being accurate about what AETHER does and does
not cover:

| Syllabus topic | Covered by AETHER? | Where |
|---|---|---|
| GenAI meaning, capabilities, applications | Yes — AETHER *is* an applied GenAI system: text generation for essays/reports/letters/code, conversational Q&A, and an agent that decides which tool a request needs. | `app/services/agent.py`, `app/core/runner.py` |
| Tools for text/code generation | Yes, directly. | `write_document` action, multiple file formats |
| Tools for image/video/audio *generation* | No. Speech is used for input (speech-to-text via faster-whisper) and output (OS text-to-speech), not generation of new audio/image/video content. | — |
| Intro to LLMs, history/evolution | Not implemented in code — covered narratively in `docs/PROJECT_REPORT.md` only. | `docs/PROJECT_REPORT.md` |
| Transformer architecture (attention, pre-training, fine-tuning, MLM/NSP) | Not implemented — these models are pretrained by the API provider; AETHER never trains, fine-tunes, or touches model internals. | — |
| Data preprocessing, training strategies, fine-tuning on custom data | Not applicable — no training happens in this project. | — |
| Text generation techniques | Yes. | `agent.generate_text`, `agent.chat` |
| **Conditional text generation** | Yes, throughout: every generation call conditions the model on a system prompt plus the user's instruction, and optionally on retrieved/attached source material (grounding context), not just a bare prompt. | `generate_text(instruction, context=...)`, `chat(message, context=...)` |
| **Sampling strategies (greedy / random / temperature / nucleus)** | Yes, two ways: (1) internally, every call picks a deliberate `temperature` per task — `0.0` for classifier/fact-verification calls (= greedy decoding), `0.1–0.6` for replies and creative writing; (2) explicitly, the desktop app's **Playground** page runs one prompt through 4 named presets (greedy, low-temperature, nucleus/top-p, high-temperature) in parallel and shows all 4 outputs side by side. Top-k and beam search are *not* available — confirmed empirically against Groq (`top_k` → `400 unsupported property`; `n>1` → `400 must be at most 1`), since both require raw logit access no hosted chat-completions API exposes. | `agent.py` `SAMPLING_PRESETS`/`generate_variant`, `POST /api/compare`, desktop Playground page |
| **Evaluation metrics for text generation (perplexity, BLEU, ROUGE)** | Yes. BLEU/ROUGE-1/2/L score generated text against a reference where one meaningfully exists (factual QA, summarization — intentionally *not* forced onto open-ended essays/poems with no single correct answer). Perplexity can't be computed from the live provider's own logprobs (Groq rejects `logprobs` outright — another hosted-API limitation, not a code gap), so it's computed by scoring the generated text with a small fixed local reference model (`distilgpt2`) instead — the standard NLG-literature workaround for exactly this situation. | `app/eval/metrics.py`, `scripts/evaluate_generation.py`, `backend/MODEL_SETUP.md` |

## Limitations
This is a prototype, not a finished commercial-grade JARVIS. It currently routes one
primary action per command. Spotify opens a search page; playback may require user
interaction. Reminders are displayed in AETHER but native Windows toast notifications
are not integrated. File search is filename-only. Speech model downloads happen on
first use. Generation quality and latency depend on the configured cloud provider and
your internet connection. RAG beyond simple keyless lookups, semantic memory, robust
multi-step planning, wake word, comprehensive browser automation, full UI control and
a signed installer remain future work.

## Safety
No arbitrary shell execution is exposed to the model. Application launching is
allowlisted. File search is read-only. Generated documents and notes are saved
locally. API keys live only in the gitignored `backend/.env` file and are never sent
anywhere except the configured provider's own API. Review important outputs before
relying on them — document/letter generation fills unknown personal details with
bracketed placeholders rather than inventing them, and factual chat replies are
grounded and cross-checked where possible, but no LLM-backed system is immune to
occasional mistakes.

## Academic presentation
- Project report: `docs/AETHER_Project_Report.pdf` and `.docx`
- Architecture: `docs/ARCHITECTURE.md`
- Test plan: `docs/TEST_CASES.md`
- Demo script: `docs/DEMO_SCRIPT.md`
- AI model/provider setup: `backend/MODEL_SETUP.md`

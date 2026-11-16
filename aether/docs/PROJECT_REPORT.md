# AETHER: A Desktop AI Assistant with Sampling-Strategy Comparison

**Project category:** Generative AI, Agentic AI and Desktop Automation  
**Target platform:** Windows 10/11  
**Implementation:** Python, FastAPI, Electron, React, TypeScript; OpenAI/Groq/Gemini (cloud) + Hugging Face Transformers (local decoding)

## Abstract
AETHER is a desktop assistant that interprets natural-language instructions and executes
selected productivity actions on a Windows computer. Application logic — action routing,
tool execution, notes, reminders, speech recognition — runs on-device; text generation
is produced by a pretrained large language model reached through a configurable cloud
API (OpenAI, Groq, or Google Gemini, switchable with one setting). Every generative
reply (chat or document writing) runs through 6 sampling strategies in parallel —
greedy, low-temperature, nucleus (top-p), and high-temperature via the live cloud model,
plus top-k sampling and beam search run as real local decoding on a small model
(`distilgpt2`), since no hosted chat-completions API exposes either — and the user picks
which output to keep, rather than the system silently choosing one. Each variant is
scored live with perplexity, a source-grounding truthfulness check, and BLEU/ROUGE
similarity to source material where one exists. A desktop chat interface presents the
conversation, task progress, and variant comparison. Local speech recognition is
provided through faster-whisper; text-to-speech uses the operating system's speech
synthesis.

## Problem statement
Most AI assistants pick one sampling configuration, hide it from the user, and present
a single answer as if it were the only possible one — while a central topic of
generative-AI coursework (greedy vs. random vs. temperature vs. nucleus vs. top-k vs.
beam search) stays invisible in the product. AETHER explores what it looks like to
surface that choice directly: generate under multiple real decoding strategies, show
the user the actual difference between them (including where a strategy drifts from the
facts), and let a human pick — rather than asserting there is one correct response.

## Objectives
1. Build a natural-language interface for desktop productivity, with local tool
   execution (notes, reminders, file discovery, app launching, document creation) kept
   separate from cloud-dependent text generation.
2. Support multiple interchangeable cloud AI providers behind one code path.
3. Make LLM sampling strategies a first-class, visible, comparable part of the product,
   not an invisible configuration default — including the two strategies (top-k, beam
   search) no hosted API exposes, by running them for real on a local model instead of
   faking them.
4. Score generated text with real, correctly-scoped evaluation metrics (perplexity,
   BLEU, ROUGE), live in the app where a reference exists and offline where a
   controlled comparison is needed.
5. Reduce hallucination through keyless factual grounding and an explicit
   fact-verification pass, surfaced to the user rather than hidden.
6. Demonstrate modular design, honest scope reporting, and verifiable execution.

## Model and provider choice
Three providers are supported through one abstraction (`app/config.py` `_PROVIDERS`,
`app/services/agent.py`): OpenAI, Groq, and Google Gemini. Groq and Gemini both expose
an API that's wire-compatible with OpenAI's chat-completions format, so all three share
one request/response code path — only the base URL, API key, and model name differ,
selected with `AETHER_PROVIDER` in `backend/.env`. Groq (free tier, no card required,
`openai/gpt-oss-120b`) is the default actually used for development and evaluation in
this report, after OpenAI's account ran out of credits and Gemini's free tier returned
`429` on every image-capable model and required an OAuth-shaped key incompatible with
the standard Bearer-auth endpoint for its text models. Provider model catalogs changed
twice during development (Groq deprecated `llama-3.3-70b-versatile`; Google deprecated
`gemini-2.0-flash`) — see `backend/MODEL_SETUP.md`'s reproducibility note.

## System architecture
The desktop client is built with Electron, React and TypeScript, served by Vite; it
talks only to a local FastAPI backend. The backend classifies each instruction into
either a deterministic tool action or a generative one. Deterministic actions (open an
app, set a reminder, search files) execute once and return. Generative actions (general
chat, document/code writing) run the 6-strategy sampling-variant engine
(`app/core/variants.py`), score each result, and pause the task at `awaiting_selection`
until the user picks one through `POST /api/tasks/{id}/select` — nothing is finalized or
written to disk before that pick. See `docs/ARCHITECTURE.md` for the full component and
sequence diagrams. Task state is stored in SQLite; notes and generated documents are
stored in local folders. Local speech-to-text uses faster-whisper. No arbitrary shell
command is generated or executed by the LLM.

## AI concepts demonstrated
- **Large language models as a service:** pretrained instruction-tuned models, reached
  through three interchangeable provider APIs, interpret requests and generate content.
  Transformer attention/pretraining/fine-tuning happen inside the provider's model;
  AETHER does not implement, train, or fine-tune any of that — used strictly as a
  black box, stated plainly rather than overclaimed (see the README's syllabus table).
- **Conditional text generation:** every generation call conditions the model on a
  system prompt, the user's instruction, and optional grounding/attached-document
  context — never a bare prompt alone.
- **Sampling strategies, made visible and comparable:** greedy decoding, low/high
  temperature sampling, and nucleus (top-p) sampling via the live cloud API; top-k
  sampling and beam search via a real local decode loop (Hugging Face Transformers'
  `generate()` on `distilgpt2`), since hosted chat-completions APIs reject both
  (confirmed against Groq: `top_k` → `400 unsupported property`; `n>1` → `400 must be
  at most 1`).
- **Evaluation metrics for generated text:** perplexity (scored by a fixed external
  reference model, since the live providers don't expose token log-probabilities),
  BLEU and ROUGE-L (scored only where a real reference answer exists — never forced
  onto open-ended creative output).
- **Grounding and hallucination mitigation:** a keyless DuckDuckGo lookup grounds
  factual questions in real source text, and a separate verification pass checks
  whether the model's specific claims are actually present in that source before
  calling them "grounded."
- **Prompt engineering:** structured system prompts constrain action classification to
  a known schema, and targeted instructions placed next to the user's own message (not
  just in the system prompt) measurably reduce specific fabrication patterns found
  during testing (invented personal details, invented résumé achievements).
- **Agentic workflow:** observe/interpret → generate multiple candidate actions →
  human selects → verify loop, rather than a single fixed pipeline.
- **Speech recognition:** faster-whisper converts recorded audio into text locally.
- **Persistence:** SQLite stores task history; local files store notes, generated
  documents, and evaluation run results.

## Main modules
| Module | Responsibility |
|---|---|
| Electron/React UI | Chat interface with inline variant picker, sidebar, Playground page, settings, notes and reminders |
| FastAPI | Application API, task endpoints, `/api/compare`, `/api/tasks/{id}/select` |
| Agent (`app/services/agent.py`) | Prompt construction, action classification, sampling-variant generation (cloud + local) |
| Variant engine (`app/core/variants.py`) | Runs all 6 presets concurrently, attaches perplexity/grounding/similarity metrics |
| Cloud provider (OpenAI / Groq / Gemini) | Hosted LLM inference for 4 of the 6 sampling strategies |
| Local model (`distilgpt2`) | Real top-k/beam-search decoding and perplexity scoring, run entirely on-device |
| Grounding (`app/tools/knowledge.py`) | Keyless DuckDuckGo lookup + fact-verification pass |
| Tool layer | Notes, reminders, desktop apps, music, files and documents |
| SQLite | Persistent task history and execution steps |
| faster-whisper | Local speech transcription |
| Evaluation harness (`backend/scripts/evaluate_generation.py`) | Offline, per-strategy BLEU/ROUGE/perplexity aggregation |

## Results and analysis

`scripts/evaluate_generation.py` ran 9 prompts (7 factual/summarization prompts with a
known reference answer, 2 open-ended) through all 6 sampling strategies via
`POST /api/compare`, scoring every output with perplexity (a fixed local `distilgpt2`
reference model) and, where a reference answer exists, BLEU and ROUGE-L. Full run:
`backend/eval_results/run_20261116T082744Z.json`.

| Strategy | Mean perplexity (n=9) | Mean BLEU (n=7) | Mean ROUGE-L (n=7) |
|---|---|---|---|
| Greedy decoding | 1542.37 | 32.88 | 0.769 |
| Low-temperature sampling | 867.13 | 33.16 | 0.757 |
| Nucleus (top-p) sampling | 815.26 | 31.60 | 0.673 |
| High-temperature random sampling | 865.08 | 41.46 | 0.803 |
| Top-k sampling (local model) | 21.35 | 0.53 | 0.041 |
| Beam search (local model) | 9.35 | 5.34 | 0.169 |

Two findings worth stating plainly:

1. **The four cloud strategies barely differ on short factual answers.** BLEU/ROUGE
   stay in the same narrow band (31–41 BLEU, 0.67–0.80 ROUGE-L) across greedy through
   high-temperature sampling — for a question with one short correct answer ("Paris"),
   the sampling strategy has little room to matter. This is the same effect the
   Playground page warns about before you even run it.
2. **Low perplexity does not mean correct.** Top-k and beam search score the *lowest*
   perplexity (9.35–21.35, far below the cloud strategies) because `distilgpt2` finds
   their rambling/repetitive local-model output highly self-predictable — yet their
   BLEU/ROUGE against the real answer collapse to near zero. Perplexity measures how
   unsurprising text is to a reference model, not whether it's right; the grounding-check
   pass (a separate true/false verification against source material, shown per variant
   in the UI) is what actually catches wrong answers — perplexity alone would have been
   misleading here.

## Safety and privacy
- The LLM cannot execute arbitrary shell commands.
- Application launching uses an allowlist.
- File search is read-only.
- No generative reply is saved or shown as final until a human picks it from the 6
  sampling variants — nothing is auto-committed on the model's behalf.
- Generated files are written to the configured output directory, with automatic
  de-duplication so an untitled document can never silently overwrite another.
- API keys live only in the gitignored `backend/.env` and are sent only to their own
  provider's API, never logged or sent anywhere else.
- External services such as Spotify, DuckDuckGo lookups, and the configured cloud AI
  provider require internet access; the app's own file/notes/reminders/speech features
  do not.

## Current scope and limitations
The present release is a functional prototype. It supports one routed action per
command rather than robust multi-step task decomposition. Spotify integration opens a
search page and does not guarantee playback. Reminders are stored and displayed in the
application, but native Windows toast notifications and recurring schedules are not yet
implemented. File discovery is filename-based and limited to Desktop, Documents and
Downloads. Image, audio, and video generation were attempted and explicitly dropped:
every image-capable model across OpenAI, Groq, and Gemini returned either no credits or
a `0` free-tier quota, and no provider in use offers audio/video generation on a free
tier. Local speech recognition downloads its model on first use. Browser automation,
semantic RAG over personal documents, wake-word detection, calendar/email integration,
full UI automation and comprehensive permission dialogs are future work.

## Testing plan
The `TEST_CASES.md` file defines reproducible functional checks, updated for the current
cloud-provider architecture and the variant-picker flow. Before a final demonstration:
install Python and Node dependencies, obtain a free API key for the configured provider
(Groq by default — see `backend/MODEL_SETUP.md`), launch the backend and Electron
client, then execute each test and record the observed result. Do not report tests as
passed until they have been run on the target machine.

## Future enhancements
1. Multi-step planner with dependency-aware execution and cancellation.
2. RAG over local PDFs and documents using embeddings and FAISS.
3. Native Windows notifications and recurring reminders.
4. Browser and desktop UI automation with explicit confirmation gates.
5. Semantic memory and conversation search.
6. A funded provider account to actually exercise the (already-built) image-generation
   code path, and investigation of free-tier audio-generation models (e.g. Groq's
   Orpheus TTS models) as a genuinely achievable next step.
7. Signed installer with bundled runtime bootstrap.

## Conclusion
AETHER demonstrates a practical architecture that combines interchangeable cloud LLM
providers, a real local decoding path for strategies no hosted API exposes, and a safe
desktop tool-execution layer — with the sampling strategy itself treated as a visible,
comparable, user-decided part of the product rather than a hidden default. Its main
contribution is making generative AI's actual decoding mechanics (and their real
trade-offs — quality vs. determinism, fluency vs. correctness) something a user directly
sees and chooses, backed by metrics that are honestly scoped to what they can and can't
measure. The prototype also creates a foundation for further study of RAG, agent
orchestration, and human-in-the-loop generation review.

## One-click deployment
The ZIP includes Windows PowerShell bootstrap scripts and BAT launchers. On first run,
the setup script checks and installs missing Python and Node.js prerequisites through
winget and installs project dependencies. Since AETHER now depends on a cloud AI API
rather than a bundled local model, the script creates `backend/.env` from
`backend/.env.example` and prompts for an API key before first launch (see
`backend/MODEL_SETUP.md`). Subsequent launches use `START_AETHER.bat`, which also warns
if the configured provider's key looks unset. This automates setup but still requires
internet for initial downloads, every AI reply, and may display Windows installer
prompts.

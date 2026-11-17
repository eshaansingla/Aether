# AETHER Classroom Demonstration (7–9 minutes)

## 1. Introduce the problem (30 seconds)
AETHER is a desktop assistant that routes natural-language commands to controlled
productivity tools. Local app logic (file actions, notes, reminders, speech) runs on the
device; text generation goes through a configured cloud AI API (OpenAI, Groq, or
Gemini - switchable with one setting, no code change).

## 2. Explain the architecture (1 minute)
Show `docs/ARCHITECTURE.md`'s component diagram. Electron UI → local FastAPI backend →
either a deterministic tool (open an app, set a reminder) or the sampling-variant
engine, which is the part worth dwelling on.

## 3. Demonstrate a generative reply and the variant picker (2 minutes)
Ask a chat question (e.g. "What is the capital of Japan?"). Show that the task pauses
at "choose a response below" with 6 cards instead of auto-answering: 4 run on the live
cloud model (greedy, low-temperature, nucleus/top-p, high-temperature), 2 run a real
local decoding loop (top-k sampling, beam search) on `distilgpt2`, since no hosted
chat-completions API exposes either - demonstrated directly: Groq rejects `top_k` with
`400 unsupported property` and rejects `n>1` with `400 must be at most 1`. Point out the
per-card metrics (perplexity, grounding check, BLEU/ROUGE-vs-source) and that beam
search's repeated text scores a *low* perplexity despite being wrong - a clean
illustration that perplexity measures predictability, not correctness.

## 4. Demonstrate the Playground page (1 minute)
Open Playground, run an open-ended prompt (e.g. "Describe a sunset in one sentence").
Show the visible quality gap between the 4 cloud strategies and the 2 local ones, and
the note explaining why top-k/beam are computed differently.

## 5. Demonstrate productivity tools (1–2 minutes)
- Create a note by natural language.
- Set a reminder.
- Launch Calculator.
- Search for a file.
- Generate a DOCX document - show the same 6-variant picker applies to document writing,
  and that the file is only saved after a variant is picked.

## 6. Demonstrate voice (30–60 seconds)
Record a short command. Explain that faster-whisper performs transcription locally.
Use the read-aloud control to demonstrate system speech synthesis.

## 7. Discuss AI concepts and results (1–2 minutes)
Reference the README's syllabus-alignment table directly: strong, demonstrated coverage
of text generation techniques, conditional generation, and sampling strategies/metrics;
explicitly no coverage of transformer internals, pretraining, or fine-tuning, since every
model is used as a pretrained black box via API - state this plainly rather than
overclaiming. Show `docs/PROJECT_REPORT.md`'s Results and analysis section: the
aggregated BLEU/ROUGE/perplexity table across 6 strategies and 9 test prompts from
`scripts/evaluate_generation.py`.

## 8. Discuss limitations and future work (30 seconds)
Mention: no image/audio/video generation (attempted - blocked by $0 free-tier quota on
every image-capable model tried); provider model catalogs can change without notice
(already hit twice during development - see `backend/MODEL_SETUP.md`'s reproducibility
note); multi-step planning and deeper browser automation remain future work. This
honest scope discussion demonstrates engineering judgement.

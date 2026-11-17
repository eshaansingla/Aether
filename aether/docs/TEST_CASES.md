# AETHER Functional Test Plan

Record actual results on the target Windows PC. A test is not considered passed until it has been executed.

| ID | Test input / action | Expected result |
|---|---|---|
| T01 | Start backend and open `/health` | JSON status reports online |
| T02 | Open `/api/status` | `api_online: true`, configured provider and model reported |
| T03 | `Take a note: Review capstone hardware list` | Markdown note appears in Notes page and local notes folder |
| T04 | `Remind me to take a break in 10 minutes` | Reminder appears with scheduled time |
| T05 | `Open Calculator` | Windows Calculator launches |
| T06 | `Play Daft Punk` | Spotify search opens for Daft Punk |
| T07 | `Find my resume` | Matching filenames in allowed folders are listed |
| T08 | `Create a Word document about renewable energy` | Task reaches `awaiting_selection` with 6 variants; picking one saves a DOCX |
| T09 | `What is the capital of France?` | Task reaches `awaiting_selection`; the 4 cloud variants agree; picking one shows "Paris." |
| T10 | Ask an obscure/unverifiable factual question with no good source | Grounding check marks the variant "Not confirmed by source" rather than a confident wrong answer |
| T11 | Open Playground, run an open-ended prompt | All 6 strategy cards render with perplexity; top-k/beam show visibly rougher text than the cloud presets |
| T12 | Click microphone and dictate a sentence | faster-whisper returns a transcript locally |
| T13 | Restart backend and reload history | Completed task records remain available from SQLite |
| T14 | Ask to run an arbitrary shell command | No shell command is executed; assistant explains unsupported action |
| T15 | Remove/blank the configured provider's API key, send a command | App reports the AI API is unreachable rather than failing silently or hanging |
| T16 | Run `python scripts/evaluate_generation.py` with the backend up | Completes, writes a timestamped run under `backend/eval_results/`, refreshes `latest_summary.md` |
| T17 | Switch `AETHER_PROVIDER` in `.env` (e.g. groq → openai) and restart the backend | `/api/status` reflects the new provider/model without code changes |
| T18 | `write essay on my cat` | All 6 cards arrive (streamed in progressively); beam/top-k show real, readable text for every one of their 5 candidates - none render blank |
| T19 | `write an email to my professor asking for an extension on my project deadline` | All 6 cards arrive; picking any candidate from beam/top-k/nucleus (not just the top-ranked default) finalizes that exact candidate's text |
| T20 | `make a poster announcing our college tech fest` | All 6 cards arrive; non-ASCII punctuation in cloud output (curly quotes, em dashes, emoji) renders correctly, not as mojibake |
| T21 | `what is the tallest mountain in the world?` | All 6 cards arrive; grounded cloud presets agree on Everest; beam/top-k show visibly rougher but non-empty text |
| T22 | `solve this: if a train travels 60 km in 45 minutes, what is its speed in km/h?` | All 6 cards arrive; low-temperature/greedy/nucleus show correct worked arithmetic (80 km/h) |
| T23 | Fire 5 of T18-T22 at once (concurrent requests) | No task's poll ever 500s; every task eventually reaches all 6 variants or a plain "(the AI provider is rate-limited right now...)" message on individual cards - never a raw exception string, and never a frozen/incomplete card list |

## Test record template
- Date:
- Windows version:
- CPU:
- GPU model / driver:
- RAM:
- AETHER_PROVIDER / configured model:
- Test ID:
- Actual result:
- Pass / fail:
- Screenshot or log reference:

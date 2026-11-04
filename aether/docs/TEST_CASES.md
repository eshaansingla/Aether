# AETHER Functional Test Plan

Record actual results on the target Windows PC. A test is not considered passed until it has been executed.

| ID | Test input / action | Expected result |
|---|---|---|
| T01 | Start backend and open `/health` | JSON status reports online |
| T02 | Start Ollama and open `/api/status` | Ollama connection and installed models are reported |
| T03 | `Take a note: Review capstone hardware list` | Markdown note appears in Notes page and local notes folder |
| T04 | `Remind me to take a break in 10 minutes` | Reminder appears with scheduled time |
| T05 | `Open Calculator` | Windows Calculator launches |
| T06 | `Play Daft Punk` | Spotify search opens for Daft Punk |
| T07 | `Find my resume` | Matching filenames in allowed folders are listed |
| T08 | `Create a Word document about renewable energy` | Local model generates content and DOCX is saved |
| T09 | Click microphone and dictate a sentence | faster-whisper returns a transcript locally |
| T10 | Restart backend and reload history | Completed task records remain available from SQLite |
| T11 | Ask to run an arbitrary shell command | No shell command is executed; assistant explains unsupported action |
| T12 | Stop Ollama and send a command | App reports local model unavailable or uses limited deterministic fallback |

## Test record template
- Date:
- Windows version:
- CPU:
- GPU model / driver:
- RAM:
- Ollama version:
- Model tag and quantisation:
- Test ID:
- Actual result:
- Pass / fail:
- Screenshot or log reference:

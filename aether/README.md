# AETHER — Local-First Desktop AI Assistant

AETHER is a Windows-first desktop assistant that routes natural-language commands to controlled productivity tools. Its language-model inference runs locally through Ollama; no paid OpenAI, Gemini, Claude or other hosted AI API key is required.

## Features in this prototype
- ChatGPT-inspired Electron + React desktop chat UI.
- Local LLM command understanding and document generation via Ollama.
- Local task history in SQLite.
- Notes saved as Markdown.
- Reminders scheduled and displayed in the app.
- Allowlisted Windows app launching.
- Spotify search launch (internet/service account may be required).
- Filename search in Desktop, Documents and Downloads.
- DOCX/TXT document creation.
- Local speech-to-text using faster-whisper.
- Read-aloud using the operating system's available speech synthesis.
- Settings page showing local runtime/model status.

## Target hardware
Designed as a practical starting point for 16 GB RAM, NVIDIA GPU with 6 GB VRAM and 256 GB free disk. Default model target is `qwen3:4b`; use `qwen3:1.7b` if the larger model is too slow or memory-constrained. Actual performance depends on exact CPU/GPU, drivers, context size and concurrent applications.

## One-click setup (Windows 10/11)

1. Extract the ZIP to a normal folder, such as `C:\\AETHER`.
2. Double-click `SETUP_AND_RUN.bat`.
3. The script automatically installs missing Python 3.11, Node.js LTS and Ollama using Windows Package Manager (winget), creates the Python environment, installs all project dependencies, downloads `qwen3:4b`, and starts AETHER.
4. For later launches, double-click `START_AETHER.bat`.

The first setup requires internet and can take a while because it downloads runtimes, packages and a multi-gigabyte local model. Windows may show installer or security prompts. If winget is unavailable, install/update **App Installer** from Microsoft Store and rerun setup.

The setup scripts are in `windows/`. The backend and desktop commands are prewritten; you do not need to type them manually.

## Example commands
- `Play some relaxing music`
- `Take a note: Finish the project report`
- `Remind me to take a break in 20 minutes`
- `Open Calculator`
- `Find my resume`
- `Create a Word document about renewable energy`

## AI concepts
See `docs/PROJECT_REPORT.md` and `docs/ARCHITECTURE.md`. AETHER uses a pretrained Transformer-family LLM. Attention and multi-head attention are internal to that model; this project does not train a Transformer or implement MHA from scratch. The project demonstrates prompt engineering, local inference, structured action routing, tool execution and a basic agentic workflow.

## Limitations
This is a prototype, not a finished commercial-grade JARVIS. It currently routes one primary action per command. Spotify opens a search page; playback may require user interaction. Reminders are displayed in AETHER but native Windows toast notifications are not integrated. File search is filename-only. Speech model downloads happen on first use. RAG, semantic memory, robust multi-step planning, wake word, comprehensive browser automation, full UI control and a signed installer remain future work.

## Safety
No arbitrary shell execution is exposed to the model. Application launching is allowlisted. File search is read-only. Generated documents and notes are saved locally. Review important outputs before relying on them.

## Academic presentation
- Project report: `docs/AETHER_Project_Report.pdf` and `.docx`
- Architecture: `docs/ARCHITECTURE.md`
- Test plan: `docs/TEST_CASES.md`
- Demo script: `docs/DEMO_SCRIPT.md`

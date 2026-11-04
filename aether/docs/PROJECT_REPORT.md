# AETHER: A Local-First Intelligent Desktop Assistant

**Project category:** Generative AI, Agentic AI and Desktop Automation  
**Target platform:** Windows 10/11  
**Implementation:** Python, FastAPI, Electron, React, TypeScript, Ollama

## Abstract
AETHER is a local-first desktop assistant designed to interpret natural-language instructions and execute selected productivity actions on a Windows computer. The system combines a locally hosted large language model with a controlled tool-execution layer. It supports note creation, reminders, allowlisted application launching, music search, filename search and document generation. A desktop chat interface presents the conversation and execution status. The architecture is designed to keep language-model inference on-device through Ollama, avoiding a dependency on paid hosted AI APIs. Local speech recognition is provided through faster-whisper, while text-to-speech uses the operating system's speech synthesis.

## Problem statement
Many AI assistants rely on cloud services and are separated from the desktop applications where users perform everyday work. AETHER explores how a local language model can interpret user intent and invoke controlled desktop tools through a single interface, while keeping personal prompts and local files on the user's device.

## Objectives
1. Build a natural-language interface for desktop productivity.
2. Run LLM inference locally without a paid cloud AI API.
3. Route user requests to a small set of safe, typed tools.
4. Support notes, reminders, file discovery, app launching and document creation.
5. Provide a conversational interface with task progress and local history.
6. Demonstrate modular design, privacy controls and verifiable execution.

## Hardware profile and model choice
The target machine has 16 GB RAM, an NVIDIA GPU with 6 GB VRAM and approximately 256 GB free storage. The default model target is Qwen3 4B in the quantised Ollama distribution. This size is a compromise between language capability and local memory. If inference is too slow or memory pressure is high, Qwen3 1.7B is the fallback. GPU layer offloading and performance depend on the exact GPU, CPU, driver, context length and other running processes; therefore, performance must be measured on the deployment machine rather than assumed.

## System architecture
The desktop client is built with Electron, React and TypeScript. It sends commands to a local FastAPI service. The local agent asks Ollama running on localhost to classify the command into a structured action. The backend validates the selected action and invokes a predefined tool. Task state and execution steps are stored in SQLite; notes and generated documents are stored in local folders. Local speech-to-text uses faster-whisper. No arbitrary shell command is generated or executed by the LLM.

### Request flow
1. User enters or dictates a command.
2. Electron frontend submits the command to the local FastAPI backend.
3. The agent requests structured JSON from the local Ollama model.
4. Backend validates the action and arguments.
5. A predefined tool performs the action.
6. The system checks the result where possible and updates task state.
7. The frontend displays the outcome and execution trace.

## AI concepts demonstrated
- **Large Language Models:** A locally hosted instruction-tuned model interprets user requests and generates document content.
- **Transformer architecture:** The selected pretrained model is based on the Transformer family. Its attention mechanisms and multi-head attention operate inside the model; AETHER does not implement or train those layers.
- **Prompt engineering:** A structured system prompt constrains the model to a known action schema and safety rules.
- **Structured generation / tool routing:** The model returns JSON specifying an action and arguments; the backend maps that action to a controlled tool.
- **Agentic workflow:** The system performs an observe/interpret → act → verify loop for a task. The current implementation is a single-action agent prototype, not a fully autonomous multi-agent planner.
- **Local inference:** Ollama serves the model on localhost, so inference does not require a cloud AI API.
- **Speech recognition:** faster-whisper converts recorded audio into text locally.
- **Persistence:** SQLite stores task history; local files store notes and generated outputs.

## Main modules
| Module | Responsibility |
|---|---|
| Electron/React UI | Chat interface, sidebar, settings, notes and reminders |
| FastAPI | Local application API and task endpoints |
| Local agent | Prompt construction, action classification and document generation |
| Ollama | On-device LLM inference |
| Tool layer | Notes, reminders, desktop apps, music, files and documents |
| SQLite | Persistent task history and execution steps |
| faster-whisper | Local speech transcription |

## Safety and privacy
- The LLM cannot execute arbitrary shell commands.
- Application launching uses an allowlist.
- File search is read-only.
- Generated files are written to the configured output directory.
- The local AI runtime is addressed through localhost.
- External services such as Spotify and websites still require internet access and their own accounts.
- The first installation/model download requires internet; inference can run offline after setup.

## Current scope and limitations
The present release is a functional prototype. It supports one routed action per command rather than robust multi-step task decomposition. Spotify integration opens a search page and does not guarantee playback. Reminders are stored and displayed in the application, but native Windows toast notifications and recurring schedules are not yet implemented. File discovery is filename-based and limited to Desktop, Documents and Downloads. Local speech recognition downloads its model on first use. Browser automation, semantic RAG over personal documents, wake-word detection, calendar/email integration, full UI automation and comprehensive permission dialogs are future work. The desktop app has not yet been validated on the target PC.

## Testing plan
The `TEST_CASES.md` file defines reproducible functional checks. Before a final demonstration, install Ollama, download the model, install Python and Node dependencies, launch the backend and Electron client, then execute each test and record the observed result. Do not report tests as passed until they have been run on the target machine.

## Future enhancements
1. Multi-step planner with dependency-aware execution and cancellation.
2. RAG over local PDFs and documents using embeddings and FAISS.
3. Native Windows notifications and recurring reminders.
4. Browser and desktop UI automation with explicit confirmation gates.
5. Semantic memory and conversation search.
6. Evaluation dashboard for task success, latency and model/tool selection accuracy.
7. Signed installer with bundled runtime bootstrap and model manager.

## Conclusion
AETHER demonstrates a practical local-first architecture that combines an LLM with safe desktop tools. Its main contribution is the integration of local language understanding, structured action routing and a desktop productivity interface. The prototype also creates a foundation for further study of RAG, agent orchestration, local inference and human-in-the-loop automation.


## One-click deployment
The ZIP includes Windows PowerShell bootstrap scripts and BAT launchers. On first run, the setup script checks and installs missing Python, Node.js and Ollama prerequisites through winget, installs project dependencies, pulls the configured local model, and launches the application. Subsequent launches use START_AETHER.bat. This automates setup but still requires internet for initial downloads and may display Windows installer prompts.

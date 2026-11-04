# AETHER Architecture and Design Notes

## Component diagram
```mermaid
flowchart TD
    U[User: text or voice] --> UI[Electron + React UI]
    UI --> API[FastAPI on localhost]
    API --> AG[Local Agent]
    AG <--> LLM[Ollama: Qwen3 4B]
    AG --> TR[Tool Registry / Controlled Dispatcher]
    TR --> DESK[Windows App Launcher]
    TR --> MUS[Spotify Search]
    TR --> FILE[File Search and Document Writer]
    TR --> NOTE[Notes and Reminders]
    API --> STT[faster-whisper local STT]
    API --> DB[(SQLite Task History)]
    NOTE --> FS[(Local Notes Folder)]
    FILE --> OUT[(Output Folder)]
```

## Task lifecycle
```mermaid
stateDiagram-v2
    [*] --> Queued
    Queued --> Understanding
    Understanding --> Executing
    Executing --> Verifying
    Verifying --> Completed
    Understanding --> Failed
    Executing --> Failed
    Verifying --> Failed
```

## Data and trust boundaries
- The Electron UI communicates only with the local backend.
- The backend calls the local Ollama service on `127.0.0.1:11434`.
- Model output is treated as untrusted data. It selects from predefined actions; it does not provide executable code.
- Tool arguments must be validated by the tool implementation.
- External websites and media providers are outside the local-only AI boundary.

## Important implementation note
The LLM does not itself operate the mouse, keyboard or operating system. It proposes a structured action. The application code decides whether that action is allowed and invokes a specific handler.

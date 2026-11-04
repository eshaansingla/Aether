# AETHER Classroom Demonstration (5–7 minutes)

## 1. Introduce the problem (30 seconds)
AETHER is a local-first desktop assistant. Instead of sending prompts to a paid cloud AI API, it runs a compact language model on the computer and connects it to a controlled set of desktop tools.

## 2. Explain the architecture (1 minute)
Show the architecture diagram. Explain that the Electron UI talks to a local FastAPI backend, the backend asks Ollama for structured JSON, and a safe dispatcher invokes a predefined tool.

## 3. Demonstrate local AI (1 minute)
Open the Settings page. Show the configured model and Ollama connection. Explain that the first model download needs internet, but inference is local after download.

## 4. Demonstrate productivity tools (2 minutes)
- Create a note by natural language.
- Set a reminder.
- Launch Calculator.
- Search for a file.
- Generate a DOCX document with the local model.

## 5. Demonstrate voice (30–60 seconds)
Record a short command. Explain that faster-whisper performs transcription locally. Use the read-aloud control to demonstrate system speech synthesis.

## 6. Discuss AI concepts (1 minute)
Explain LLMs, Transformer attention and MHA (inside the pretrained model), prompt engineering, structured JSON tool routing, agentic execution and local inference. Be clear that AETHER uses a pretrained Transformer model; it does not train or implement MHA from scratch.

## 7. Discuss limitations and future work (30 seconds)
Mention multi-step planning, RAG, native notifications, deeper browser automation and stronger evaluation as next steps. This honest scope discussion demonstrates engineering judgement.

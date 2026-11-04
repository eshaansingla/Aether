# Local model setup (no cloud AI API)

AETHER uses Ollama over localhost. It does not require an OpenAI/Gemini/Claude API key.

## Recommended for this PC
- 16 GB system RAM
- NVIDIA GPU with 6 GB VRAM
- 256 GB free disk

Primary model: `qwen3:4b` (quantised Ollama build). It may share work between GPU and system RAM depending on available VRAM and context length. Start with a modest context window and close GPU-heavy applications.
Fallback: `qwen3:1.7b` if 4B is too slow or memory constrained.

## Install and download once
1. Install Ollama for Windows from https://ollama.com/download
2. Open PowerShell:
   ```powershell
   ollama pull qwen3:4b
   ollama run qwen3:4b
   ```
3. Exit the interactive model with `/bye`. Keep Ollama running in the background.
4. If the 4B model is too slow:
   ```powershell
   ollama pull qwen3:1.7b
   ```
5. Set `AETHER_MODEL=qwen3:1.7b` in `backend/.env` to use the fallback.

The first download needs internet. After model download and dependency installation, text inference runs locally. No prompt is sent to a hosted AI provider.

## Memory expectations
A quantised 4B model is a practical target, not a guarantee that all model weights and runtime state fit inside 6 GB VRAM. Ollama can offload layers to system RAM. Actual speed depends on the exact NVIDIA GPU, driver, CPU, context length and other running applications. Avoid claiming a fixed tokens/second figure without measuring the target machine.

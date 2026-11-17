AETHER - START HERE

FIRST TIME ONLY:
1. Extract the complete ZIP to a normal folder, e.g. C:\AETHER.
2. Get a free API key, e.g. Groq (no card needed): https://console.groq.com/keys.
3. Double-click SETUP_AND_RUN.bat.
4. Accept any Windows/winget installer prompts.
5. Wait for Python, Node.js and the project packages to install.
6. Open backend\.env, set AETHER_PROVIDER (default groq) and paste your API key into
   the matching *_API_KEY line.
7. Rerun SETUP_AND_RUN.bat (or double-click START_AETHER.bat). AETHER starts.

EVERY TIME AFTER:
Double-click START_AETHER.bat.

IMPORTANT:
- Initial setup requires internet, as does every AI reply afterward - AETHER calls a
  cloud AI API (OpenAI, Groq, or Gemini) for text generation; it does not run a model
  locally.
- Your API key lives only in backend\.env on this machine and is never committed to git.
- Keep the two terminal windows open while using AETHER.
- Close those terminal windows to stop the backend and desktop dev server.
- This setup script installs prerequisites automatically; it cannot make a Windows PC
  run Python/Node without installing those runtimes.
- The app is still a development build. It is not yet a signed single-file installer.

import json, re
import httpx
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_FAST_MODEL

ACTIONS = "write_document,take_note,set_reminder,open_app,play_music,search_files,open_website,system_control,ask_chatgpt,general"
SYSTEM_COMMAND_LIST = "wifi_on,wifi_off,lock,mute,volume_up,volume_down,sleep,screenshot"
DOC_FORMAT_LIST = "docx,txt,md,csv,json,py,js,ts,html,css,java,c,cpp,sh,yaml,xml"

QUESTION_STARTERS = {"what","who","when","where","why","how","is","are","does","do","did",
                      "can","could","would","will","should","which","whose"}
ACTION_KEYWORDS = {
    "search_files": ("find","search","locate","file","resume","document","folder","desktop","downloads"),
    "open_app": ("open","launch","start"),
    "write_document": ("write","create","draft","essay","report","letter","document","note","script","code","save"),
    "play_music": ("play","music","song","listen","spotify"),
    "take_note": ("note",),
    "set_reminder": ("remind","reminder"),
    "system_control": ("wifi","wi-fi","volume","mute","lock","sleep","screenshot"),
    "ask_chatgpt": ("chatgpt","gpt"),
    "open_website": ("open","website","go to","http"),
}

SYSTEM = f'''
You are AETHER, a private Windows desktop assistant. Classify the user's message into exactly one action:
{ACTIONS}.
Return only a JSON object with keys:
action, title, content, app, query, minutes, url, format, command, response.
Never create shell commands or execute arbitrary code. Never delete files, send messages, make purchases,
or submit forms. Notes must preserve the dictated content. For reminders, convert explicit durations to
integer minutes; if ambiguous, ask a question in response and use general. For app launching, only use:
Notepad, Calculator, Paint, File Explorer, Chrome, Edge, Spotify, YouTube Music, ChatGPT, VS Code.
For music, use play_music.
For write_document, use it for ANY request to produce a saved, downloadable file: essays, reports, letters,
notes-to-file, code snippets/scripts, or data files. Set "content" to the user's full request (topic plus any
instructions, verbatim) so it can be expanded into the complete file, "title" to a short filename-friendly
name, and "format" to the best-fitting extension from: {DOC_FORMAT_LIST} (default "docx" for prose documents,
"md" for notes/readme-style text, or the matching language extension for code).
For system_control (Wi-Fi on/off, locking the PC, muting or changing volume, sleep, taking a screenshot), set
"command" to exactly one of: {SYSTEM_COMMAND_LIST}.
For ask_chatgpt, use it only when the user explicitly asks to ask/prompt/query ChatGPT itself (not just open
the ChatGPT app); set "content" to the exact prompt to send it. Use open_app with app=ChatGPT instead when the
user just wants the ChatGPT website opened.
Use "general" for any ordinary conversation, question, or chit-chat that isn't one of the other actions — a
separate step produces the actual reply, so you only need to classify here; leave "response" empty unless the
request is ambiguous and you need to ask a clarifying question instead of acting.
If a command requests multiple actions, select the first safe action and mention the next step in response;
the orchestrator can be extended to multi-step plans later.
'''

CHAT_SYSTEM = '''
You are AETHER, a private, helpful assistant running entirely on the user's own computer through a local
language model — no cloud AI service is involved. Hold a natural, accurate, concise conversation. Do not
fabricate facts, statistics, quotations, or references; say plainly when you are unsure. If the user's request
would actually need AETHER to take an action (open an app, change a system setting, save a file, set a
reminder, search files, play music, or ask ChatGPT), tell them they can just ask directly in the same chat and
AETHER will do it — you are only the conversational reply here, not the one performing actions.
'''

class LocalAgent:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.model = OLLAMA_MODEL
        self.fast_model = OLLAMA_FAST_MODEL

    def is_available(self):
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=2.5)
            r.raise_for_status()
            return True
        except Exception:
            return False

    def list_models(self):
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3)
            r.raise_for_status()
            return [m.get("name") for m in r.json().get("models", [])]
        except Exception:
            return []

    def understand(self, text):
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.fast_model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": text}
                    ],
                    "options": {"temperature": 0.1, "num_predict": 220},
                    "think": False
                },
                timeout=60
            )
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "{}")
            data = json.loads(raw)
            if data.get("action") not in ACTIONS.split(","):
                raise ValueError("The local model returned an unsupported action.")
        except Exception:
            data = self._fallback(text)
        return self._sanity_check(text, data)

    # A small local model occasionally misclassifies an ordinary question (e.g. "What's the
    # capital of France?") as a tool action like search_files, which would then run that tool
    # on unrelated text. If the message reads as a plain question and contains none of the
    # action's own trigger words, fall back to a normal conversational reply instead.
    def _sanity_check(self, text, data):
        action = data.get("action")
        keywords = ACTION_KEYWORDS.get(action)
        if keywords and self._looks_like_question(text):
            low = text.lower()
            if not any(k in low for k in keywords):
                return {"action": "general"}
        return data

    @staticmethod
    def _looks_like_question(text):
        low = text.strip().lower()
        if low.endswith("?"):
            return True
        first = low.split(" ", 1)[0].strip(",.!") if low else ""
        return first in QUESTION_STARTERS

    def chat(self, message, history=None):
        messages = [{"role": "system", "content": CHAT_SYSTEM}]
        for item in (history or [])[-20:]:
            role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "messages": messages,
                    "options": {"temperature": 0.6},
                    "think": False
                },
                timeout=180
            )
            r.raise_for_status()
            text = r.json().get("message", {}).get("content", "").strip()
            return text or "I don't have a response for that right now."
        except Exception:
            return ("The local AI model is not reachable right now. Make sure Ollama is running "
                     "and the configured model is installed, then try again.")

    def generate_text(self, instruction):
        r = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content":
                     "You are AETHER's writing assistant. Produce accurate, well-structured content. "
                     "Do not fabricate facts, statistics, quotations or references. State uncertainty clearly."},
                    {"role": "user", "content": instruction}
                ],
                "options": {"temperature": 0.45},
                "think": False
            },
            timeout=240
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()

    def _fallback(self, text):
        s = text.strip()
        low = s.lower()
        if re.search(r"(?i)\b(ask|prompt|query)\s+chatgpt\b", s):
            content = re.sub(r"(?i)^(ask|prompt|query)\s+chatgpt\s*(to|that|about|:)?\s*", "", s)
            return {"action":"ask_chatgpt","content":content or s}
        if re.search(r"\b(turn on|enable|connect)\b.*\bwi[\s-]?fi\b", low):
            return {"action":"system_control","command":"wifi_on"}
        if re.search(r"\b(turn off|disable|disconnect)\b.*\bwi[\s-]?fi\b", low):
            return {"action":"system_control","command":"wifi_off"}
        if re.search(r"\b(lock)\b.*\b(pc|computer|screen|workstation)\b", low):
            return {"action":"system_control","command":"lock"}
        if re.search(r"\bmute\b", low):
            return {"action":"system_control","command":"mute"}
        if re.search(r"\bvolume\s*up|turn\s*up\s*the\s*volume|louder\b", low):
            return {"action":"system_control","command":"volume_up"}
        if re.search(r"\bvolume\s*down|turn\s*down\s*the\s*volume|quieter\b", low):
            return {"action":"system_control","command":"volume_down"}
        if re.search(r"\b(play|listen to)\b", low):
            q = re.sub(r"(?i)\b(play|listen to|some|song|music)\b", "", s).strip()
            return {"action":"play_music","query":q}
        if re.search(r"\b(take a note|note this|write this down|remember this note)\b", low):
            content = re.sub(r"(?i)^(take a note|note this|write this down|remember this note)[: ,]*", "", s)
            return {"action":"take_note","title":"Quick note","content":content}
        m = re.search(r"(?i)(?:remind me to|set a reminder to)\s+(.+?)\s+in\s+(\d+)\s+(minute|minutes|min|hour|hours)", s)
        if m:
            mins = int(m.group(2)) * (60 if m.group(3).startswith("hour") else 1)
            return {"action":"set_reminder","content":m.group(1),"minutes":mins}
        m = re.search(r"(?i)\b(open|launch|start)\s+(notepad|calculator|paint|file explorer|explorer|chrome|edge|spotify|youtube music|chatgpt|vscode|vs code)\b", s)
        if m:
            app = "VS Code" if m.group(2).lower() in ("vs code","vscode") else m.group(2)
            return {"action":"open_app","app":app}
        m = re.search(r"(?i)(?:find|search for)\s+(?:the file\s+)?(.+)", s)
        if m:
            return {"action":"search_files","query":m.group(1)}
        if re.search(r"(?i)\b(write|create|draft)\b", s) and re.search(r"(?i)\b(document|essay|report|letter|word file)\b", s):
            return {"action":"write_document","title":"AETHER document","content":s,"format":"docx"}
        return {"action":"general","response":
            "The local AI model is not available yet. Start Ollama and download the configured model, or try a supported command such as 'Take a note: …'."}

agent = LocalAgent()

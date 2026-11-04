import json, re
import httpx
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_FAST_MODEL

ACTIONS = "write_document,take_note,set_reminder,open_app,play_music,search_files,open_website,system_control,ask_chatgpt,general"
SYSTEM_COMMAND_LIST = "wifi_on,wifi_off,lock,mute,volume_up,volume_down,volume_set,brightness_up,brightness_down,brightness_set,sleep,screenshot"
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
    "system_control": ("wifi","wi-fi","volume","brightness","mute","lock","sleep","screenshot"),
    "ask_chatgpt": ("chatgpt","gpt"),
    "open_website": ("open","website","go to","http"),
}

SYSTEM = f'''
You are AETHER, a private Windows desktop assistant. Classify only the LAST user message into exactly one
action: {ACTIONS}. Any earlier messages shown are just conversation history, there to help you resolve a
reference like "it", "that", or "again" in the last message — never classify or act on an earlier message
itself.
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
For system_control (Wi-Fi on/off, locking the PC, muting/volume/brightness, sleep, taking a screenshot), set
"command" to exactly one of: {SYSTEM_COMMAND_LIST}. Use the "_set" variant with an exact percentage when one is
given (e.g. "set volume to 30%"), otherwise the "_up"/"_down" variant for a relative change.
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
language model — no cloud AI service is involved.

Answer like a sharp, direct person would, not a customer-service script. Lead with the actual answer, not a
restatement of the question or a throat-clearing opener ("Great question!", "I'd be happy to help!"). Match
the length of your reply to what was actually asked — a quick factual question gets a sentence or two, not a
five-paragraph essay; a genuinely complex question gets the space it needs, organized with short paragraphs
or a list only when that structure actually helps rather than as decoration. Don't pad the end with "Let me
know if you have any other questions!" or similar filler — just stop when you're done.

Do not fabricate facts, statistics, quotations, or sources; say plainly when you're unsure rather than
guessing with false confidence. If the request is ambiguous, ask the one clarifying question that actually
unblocks you instead of guessing wrong or listing every possible interpretation.

If the user's request would actually need AETHER to take an action (open an app, change a system setting,
save a file, set a reminder, search files, play music, or ask ChatGPT), tell them they can just ask directly
in the same chat and AETHER will do it — you are only the conversational reply here, not the one performing
actions.
'''

WRITER_SYSTEM = '''
You write finished content, not a chat reply. Output ONLY the requested content itself, starting
directly with it — no greeting, no preamble such as "Sure, here's...", no meta-commentary about what
you're about to write, no sign-off, no follow-up question offering further help, and never a restated
or paraphrased copy of the request itself as a line of the output.

You never refuse and never explain what you can't do (e.g. "I don't have access to real-time
information", "I can't check their availability") — you have no ability to ask the user a clarifying
question here, so you must always produce the actual finished document directly, working around any
missing information rather than stopping to mention it.

Two different kinds of requests need two different responses to missing information:
- A letter, email, or message addressed to someone (e.g. "write an email to my professor asking for
  a meeting"): fill in every concrete detail that would normally be personal — the recipient's name,
  sender's name, course, date, time, subject — with a clearly bracketed placeholder like
  [Professor's Name], [Your Name], [Course Name], [Proposed Date/Time], written exactly where that
  detail belongs, so the user can find-and-replace it. Still write the complete, properly structured
  letter/email around those placeholders — greeting, body, sign-off — never a description of how to
  write one.
- A general composition with no addressee (e.g. "an essay about dogs", "a report on renewable
  energy"): if the request has no personal specifics, write a general, factual piece about that
  topic. Never invent a specific name, person, pet, or personal anecdote that was not given in the
  request to make it feel personal — that is fabrication, not a placeholder situation. A phrase like
  "my dog" or "my trip" with no further detail given is still a general topic (dogs, travel), not an
  invitation to invent one; write about the topic itself rather than pretending one exists.

Do not fabricate facts, statistics, quotations, or citations; write generally instead of inventing
specifics you are unsure of. Match the requested format: an essay is structured prose with an
introduction, body, and conclusion; notes are concise; a report is organized with clear sections.
Write a complete piece proportional to what was asked — substantial when asked for an essay or
report, short when asked for a quick note or message.
'''

WRITER_CODE_SYSTEM = '''
You write only the source code for the requested file. Output must be ready to save directly as the
file's content: no explanation before or after it, no markdown code fence, no commentary — just the
code, correct and complete for what was asked. Use comments inside the code only where they explain
something genuinely non-obvious.
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

    def understand(self, text, history=None):
        # A short slice of recent turns so a follow-up like "turn it up more" or "do that
        # again" can actually be classified correctly — without this the classifier sees
        # each message in total isolation and has no way to resolve what "it"/"that" means.
        context_messages = []
        for item in (history or [])[-4:]:
            role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if role in ("user", "assistant") and content:
                context_messages.append({"role": role, "content": content[:400]})
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.fast_model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        *context_messages,
                        {"role": "user", "content": text}
                    ],
                    "options": {"temperature": 0.1, "num_predict": 220, "num_ctx": 4096},
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
        data = self._chat_only_override(text, data)
        return self._sanity_check(text, data)

    # If the user explicitly says they just want the answer in chat ("just tell me",
    # "in chat", "don't save a file", "no document"), that overrides write_document even
    # though the request would otherwise look like one (e.g. still mentions "document" or
    # "write") — the model can't be trusted to catch this nuance reliably on its own.
    _CHAT_ONLY = re.compile(
        r"(?i)\b(in\s+chat\s+only|in\s+chat|just\s+(tell|answer|reply|say)|"
        r"no\s+(file|doc|document)|don'?t\s+(save|make|create)\s+(a\s+)?(file|doc|document)|"
        r"without\s+(saving|a\s+file|making\s+a\s+file))\b"
    )

    def _chat_only_override(self, text, data):
        if data.get("action") == "write_document" and self._CHAT_ONLY.search(text):
            return {"action": "general"}
        return data

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

    def chat(self, message, history=None, context=None):
        messages = [{"role": "system", "content": CHAT_SYSTEM}]
        if context:
            messages.append({"role": "system", "content":
                "The user has attached the following document(s) to this conversation. Use them to "
                "answer questions, discuss, summarize, or help edit as asked. Only state what is "
                "actually in them — never invent content that isn't there.\n\n" + context})
        for item in (history or [])[-20:]:
            role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        # Ollama defaults to a 2048-token context window regardless of what the model
        # actually supports — with up to 20 prior turns in play, that's not enough; a
        # longer-running conversation would silently lose its earlier turns rather than
        # erroring. An attached document needs more still.
        options = {"temperature": 0.6, "num_ctx": 8192 if context else 4096}
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "messages": messages,
                    "options": options,
                    "think": False
                },
                timeout=180
            )
            r.raise_for_status()
            text = self._strip_think(r.json().get("message", {}).get("content", ""))
            return text or "I don't have a response for that right now."
        except Exception:
            return ("The local AI model is not reachable right now. Make sure Ollama is running "
                     "and the configured model is installed, then try again.")

    _CODE_FORMATS = {"py", "js", "ts", "html", "css", "java", "c", "cpp", "sh", "yaml", "json", "xml"}

    @staticmethod
    def _strip_think(text):
        # qwen3 is a hybrid-thinking model: some Ollama versions still let its reasoning
        # leak into the message content even with think:False in the request — sometimes
        # as a full <think>...</think> block, sometimes as bare reasoning text with only
        # the closing </think> tag present (the opening one gets eaten by the template).
        # Either way, anything up to and including the last </think> is reasoning, not
        # the answer, and would otherwise end up saved straight into the output file.
        idx = text.rfind("</think>")
        return (text[idx + len("</think>"):] if idx != -1 else text).strip()

    def generate_text(self, instruction, fmt="docx", context=None):
        # Small local instruct models readily drift into a chatty reply (greeting, "feel
        # free to ask!", a fabricated persona addressed as "you") instead of writing the
        # actual document, especially on a short, detail-free prompt like "an essay about
        # my dog" — the model has no real dog to describe, so it invents one and replies
        # as if continuing a conversation. The system prompt has to rule that out directly.
        is_code = fmt in self._CODE_FORMATS
        system = WRITER_CODE_SYSTEM if is_code else WRITER_SYSTEM
        user_content = instruction
        options = {"temperature": 0.4, "num_predict": 1400, "num_ctx": 4096}
        if context:
            system += (
                "\n\nSource document(s) are given below the task, each between triple quotes. Base "
                "your output accurately on them: preserve their real facts and structure, and only "
                "change what the task asks you to change (e.g. summarizing, rewriting, expanding, "
                "removing a section). Do not invent content that isn't in the source unless the task "
                "explicitly asks for new original material."
            )
            user_content = f"{context}\n\nTask: {instruction}"
            options["num_ctx"] = 8192
        r = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content}
                ],
                "options": options,
                "think": False
            },
            timeout=240
        )
        r.raise_for_status()
        text = self._strip_think(r.json().get("message", {}).get("content", ""))
        return self._strip_code_fence(text) if is_code else text

    @staticmethod
    def _strip_code_fence(text):
        # Models often wrap code in a ```lang fence even when told not to; a file saved
        # with the fence still intact wouldn't run, so unwrap it defensively.
        m = re.match(r"^```[a-zA-Z0-9_+-]*\n([\s\S]*?)\n?```\s*$", text.strip())
        return m.group(1) if m else text

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

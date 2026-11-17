import json, re, time
import httpx
from app.config import AI_API_KEY, AI_BASE_URL, AI_MODEL, AI_FAST_MODEL

ACTIONS = "write_document,generate_image,take_note,set_reminder,open_app,play_music,search_files,open_website,system_control,ask_chatgpt,general"
SYSTEM_COMMAND_LIST = "wifi_on,wifi_off,lock,mute,volume_up,volume_down,volume_set,brightness_up,brightness_down,brightness_set,sleep,screenshot"
DOC_FORMAT_LIST = "docx,txt,md,csv,json,py,js,ts,html,css,java,c,cpp,sh,yaml,xml"

QUESTION_STARTERS = {"what","who","when","where","why","how","is","are","does","do","did",
                      "can","could","would","will","should","which","whose"}
ACTION_KEYWORDS = {
    "search_files": ("find","search","locate","file","resume","document","folder","desktop","downloads"),
    "open_app": ("open","launch","start"),
    "write_document": ("write","create","draft","essay","report","letter","document","note","script","code","save"),
    "generate_image": ("image","picture","photo","draw","drawing","illustration","generate","art"),
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
reference like "it", "that", or "again" in the last message - never classify or act on an earlier message
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
For generate_image, use it for ANY request to draw/generate/create a picture, image, illustration, or art.
Set "content" to a clear, concrete visual description suitable for an image generator (expand a vague request
like "a cat" into something like "a photo of an orange tabby cat sitting on a windowsill"); never use this for
a request to find/open an existing image file (that's search_files/open_app) or to write text about a topic
(that's write_document/general).
For system_control (Wi-Fi on/off, locking the PC, muting/volume/brightness, sleep, taking a screenshot), set
"command" to exactly one of: {SYSTEM_COMMAND_LIST}. Use the "_set" variant with an exact percentage when one is
given (e.g. "set volume to 30%"), otherwise the "_up"/"_down" variant for a relative change.
For ask_chatgpt, use it only when the user explicitly asks to ask/prompt/query ChatGPT itself (not just open
the ChatGPT app); set "content" to the exact prompt to send it. Use open_app with app=ChatGPT instead when the
user just wants the ChatGPT website opened.
Use "general" for any ordinary conversation, question, or chit-chat that isn't one of the other actions - a
separate step produces the actual reply, so you only need to classify here; leave "response" empty unless the
request is ambiguous and you need to ask a clarifying question instead of acting.
If a command requests multiple actions, select the first safe action and mention the next step in response;
the orchestrator can be extended to multi-step plans later.
'''

CHAT_SYSTEM = '''
You are AETHER, a private desktop assistant. Your replies are generated through a cloud AI API; the rest
of AETHER (file actions, task execution, notes, reminders, app launching) runs locally on the user's device.

Answer like a sharp, direct person would, not a customer-service script. Lead with the actual answer, not a
restatement of the question or a throat-clearing opener ("Great question!", "I'd be happy to help!"). Match
the length of your reply to what was actually asked - a quick factual question gets a sentence or two, not a
five-paragraph essay; a genuinely complex question gets the space it needs, organized with short paragraphs
or a list only when that structure actually helps rather than as decoration. Don't pad the end with "Let me
know if you have any other questions!" or similar filler - just stop when you're done.

Do not fabricate facts, statistics, quotations, or sources; say plainly when you're unsure rather than
guessing with false confidence. If the request is ambiguous, ask the one clarifying question that actually
unblocks you instead of guessing wrong or listing every possible interpretation.

If the user's request would actually need AETHER to take an action (open an app, change a system setting,
save a file, set a reminder, search files, play music, or ask ChatGPT), tell them they can just ask directly
in the same chat and AETHER will do it - you are only the conversational reply here, not the one performing
actions.
'''

WRITER_SYSTEM = '''
You write finished content, not a chat reply. Output ONLY the requested content itself, starting
directly with it - no greeting, no preamble such as "Sure, here's...", no meta-commentary about what
you're about to write, no sign-off, no follow-up question offering further help, and never a restated
or paraphrased copy of the request itself as a line of the output.

You never refuse and never explain what you can't do (e.g. "I don't have access to real-time
information", "I can't check their availability") - you have no ability to ask the user a clarifying
question here, so you must always produce the actual finished document directly, working around any
missing information rather than stopping to mention it.

Two different kinds of requests need two different responses to missing information:
- A letter, email, or message addressed to someone (e.g. "write an email to my professor asking for
  a meeting", "write an email applying for an internship"): fill in every concrete detail that would
  normally be personal - the recipient's name, sender's name, course, date, time, subject - with a
  clearly bracketed placeholder like [Professor's Name], [Your Name], [Course Name], [Proposed
  Date/Time], written exactly where that detail belongs, so the user can find-and-replace it. This
  applies just as much to claimed accomplishments, skills, employers, project names, and metrics in a
  job/internship application as it does to a name or date - a sentence like "I built a REST API used
  by 2,000+ users" is a specific, checkable factual claim about the sender exactly like a name is;
  inventing the number or the project is fabricating a résumé claim, not filling in reasonable detail.
  Use a placeholder like [a specific project or achievement, e.g. built X / led Y / improved Z by N%]
  instead. Still write the complete, properly structured letter/email around those placeholders - 
  greeting, body, sign-off - never a description of how to write one.
- A general composition with no addressee (e.g. "an essay about dogs", "a report on renewable
  energy"): if the request has no personal specifics, write a general, factual piece about that
  topic. Never invent a specific name, person, pet, or personal anecdote that was not given in the
  request to make it feel personal - that is fabrication, not a placeholder situation. A phrase like
  "my dog" or "my trip" with no further detail given is still a general topic (dogs, travel), not an
  invitation to invent one; write about the topic itself rather than pretending one exists.

Do not fabricate facts, statistics, quotations, or citations; write generally instead of inventing
specifics you are unsure of. Match the requested format: an essay is structured prose with an
introduction, body, and conclusion; notes are concise; a report is organized with clear sections.
Write a complete piece proportional to what was asked - substantial when asked for an essay or
report, short when asked for a quick note or message.
'''

WRITER_CODE_SYSTEM = '''
You write only the source code for the requested file. Output must be ready to save directly as the
file's content: no explanation before or after it, no markdown code fence, no commentary - just the
code, correct and complete for what was asked. Use comments inside the code only where they explain
something genuinely non-obvious.
'''

class LocalAgent:
    def __init__(self):
        self.base_url = AI_BASE_URL
        self.api_key = AI_API_KEY
        self.model = AI_MODEL
        self.fast_model = AI_FAST_MODEL

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    def _complete(self, model, messages, temperature, max_tokens=None, json_mode=False, top_p=None, timeout=60):
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        payload = {"model": model, "messages": messages, "temperature": temperature}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if top_p is not None:
            payload["top_p"] = top_p
        # A free-tier provider's per-minute rate limit is easy to hit in a short burst
        # (several AETHER actions in a row each make 1-2 calls) and recovers within
        # seconds - surfacing that as "the API isn't reachable" to the user would be
        # wrong when a one-second wait and retry would have just worked.
        # 5 attempts with growing backoff (and the provider's own Retry-After header,
        # when it sends one, takes priority over the guess) - a single chat/document
        # reply already fires 4 of these concurrently (one per cloud preset), plus 5
        # more for nucleus's independent samples, so a burst of 429s under real load is
        # the normal case to recover from, not an edge case.
        max_attempts = 5
        for attempt in range(max_attempts):
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            )
            if r.status_code == 429 and attempt < max_attempts - 1:
                retry_after = r.headers.get("retry-after")
                try:
                    wait = float(retry_after) if retry_after else 1.5 * (2 ** attempt)
                except ValueError:
                    wait = 1.5 * (2 ** attempt)
                time.sleep(min(wait, 20))
                continue
            r.raise_for_status()
            return (r.json()["choices"][0]["message"].get("content") or "").strip()

    def is_available(self):
        if not self.api_key:
            return False
        try:
            r = httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self):
        return sorted({self.model, self.fast_model}) if self.is_available() else []

    def understand(self, text, history=None):
        # A short slice of recent turns so a follow-up like "turn it up more" or "do that
        # again" can actually be classified correctly - without this the classifier sees
        # each message in total isolation and has no way to resolve what "it"/"that" means.
        context_messages = []
        for item in (history or [])[-4:]:
            role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if role in ("user", "assistant") and content:
                context_messages.append({"role": role, "content": content[:400]})
        try:
            raw = self._complete(
                self.fast_model,
                [
                    {"role": "system", "content": SYSTEM},
                    *context_messages,
                    {"role": "user", "content": text}
                ],
                temperature=0.1, max_tokens=220, json_mode=True, timeout=30,
            )
            data = json.loads(raw or "{}")
            if data.get("action") not in ACTIONS.split(","):
                raise ValueError("The model returned an unsupported action.")
        except Exception:
            data = self._fallback(text)
        data = self._chat_only_override(text, data)
        return self._sanity_check(text, data)

    # If the user explicitly says they just want the answer in chat ("just tell me",
    # "in chat", "don't save a file", "no document"), that overrides write_document even
    # though the request would otherwise look like one (e.g. still mentions "document" or
    # "write") - the model can't be trusted to catch this nuance reliably on its own.
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

    _INFO_REQUEST = re.compile(r"(?i)^\s*(tell me (more )?about|explain|describe|give me (info|information) (on|about))\b")

    @staticmethod
    def _looks_like_question(text):
        low = text.strip().lower()
        if low.endswith("?"):
            return True
        if LocalAgent._INFO_REQUEST.search(text):
            return True
        first = low.split(" ", 1)[0].strip(",.!") if low else ""
        return first in QUESTION_STARTERS

    def chat(self, message, history=None, context=None):
        messages = [{"role": "system", "content": CHAT_SYSTEM}]
        if context:
            messages.append({"role": "system", "content":
                "The following reference material (either attached by the user, or looked up to help "
                "answer accurately) is available for this reply. Ground your answer in it rather than "
                "your own memory. Never state a specific name, date, number, or other concrete fact "
                "unless that exact fact is written in the material below - if it only covers the "
                "general topic but not the specific detail asked (e.g. it describes an organization but "
                "never names the person the question asks about), say plainly that the detail isn't in "
                "what you have rather than filling the gap with your own guess, even a plausible-sounding "
                "one.\n\n" + context})
        for item in (history or [])[-20:]:
            role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        # Same fabrication risk as generate_text() for a job/internship application that
        # the classifier happens to route here (general chat) instead of to write_document
        # - the reminder has to apply wherever this kind of request actually lands.
        final_content = message
        if self._APPLICATION_LETTER.search(message):
            final_content += self._FABRICATION_REMINDER
        messages.append({"role": "user", "content": final_content})
        # A grounded reply needs to stick closely to the given material rather than
        # improvise - a lower temperature reduces how often the model still states an
        # unsupported specific despite the instruction above, though a model can still
        # occasionally ignore it, which is what the verification pass below catches.
        try:
            text = self._complete(
                self.model, messages,
                temperature=0.2 if context else 0.6, max_tokens=900, timeout=60,
            )
            if not text:
                return "I don't have a response for that right now."
            # Even a frontier model will occasionally state a specific, plausible-sounding
            # wrong name/date/number with full confidence rather than say it doesn't know.
            # A second pass asking a narrower yes/no question ("is this specific fact
            # actually written in the material?") is a task models handle far more
            # reliably than open-ended generation, so it catches what the system prompt
            # alone did not.
            if context:
                verdict = self._verify_grounded(context, message, text)
                if not verdict["supported"]:
                    # Surfacing the fetched material is only useful when it's actually
                    # about the thing being asked - a lookup on a vague or mistyped
                    # subject can resolve to a completely different, unrelated entity
                    # (e.g. a one-letter subject landing on a dictionary entry for that
                    # letter), and showing that alongside an apology reads as more
                    # confidently wrong than just admitting there's nothing reliable.
                    if verdict["relevant"]:
                        return (
                            "I can't confirm that specific detail from what I have - stating it "
                            "would risk giving you a made-up answer. Here's the reference material "
                            "I did find, which may still help:\n\n" + context
                        )
                    return "I don't have reliable information to answer that."
            return text
        except Exception:
            return ("The AI API is not reachable right now. Check that OPENAI_API_KEY is set "
                     "correctly in the backend's .env file and that you have network access, "
                     "then try again.")

    # The decoding strategies an OpenAI-compatible chat-completions API actually exposes:
    # temperature and top_p (nucleus) are standard parameters every provider tested here
    # accepts. top_k and beam search are NOT exposed by any of them (confirmed against
    # Groq: `top_k` → 400 "unsupported property"; `n>1` → 400 "must be at most 1") - both
    # need direct access to the raw per-token logit distribution during decoding, which a
    # hosted inference API deliberately doesn't expose. Those two presets are marked
    # kind="local": generate_variant_any() runs them through a small local model instead
    # (metrics.generate_topk/generate_beam) rather than the cloud API, since that's the
    # only way to run them for real rather than faking the output.
    SAMPLING_PRESETS = [
        {"key": "greedy", "label": "Greedy decoding", "kind": "cloud", "temperature": 0.0, "top_p": 1.0,
         "note": "Always picks the single most likely next token - deterministic, same output every time."},
        {"key": "low_temp", "label": "Low-temperature sampling", "kind": "cloud", "temperature": 0.3, "top_p": 1.0,
         "note": "Samples from the full distribution but sharply favors likely tokens - mostly conservative, slight variation."},
        {"key": "nucleus", "label": "Nucleus (top-p) sampling", "kind": "cloud", "temperature": 0.8, "top_p": 0.9,
         "note": "Samples only from the smallest set of tokens whose probabilities sum to 90%, excluding the unlikely long tail."},
        {"key": "high_temp", "label": "High-temperature random sampling", "kind": "cloud", "temperature": 1.0, "top_p": 1.0,
         "note": "Flattens the distribution before sampling - most diverse/creative, least predictable, highest risk of drifting off-topic."},
        {"key": "top_k", "label": "Top-k sampling", "kind": "local", "top_k": 50,
         "note": "Samples only from the 50 most likely next tokens at each step. Run locally on a small model (distilgpt2) since no hosted API exposes top-k - expect rougher, less coherent output than the cloud presets above."},
        {"key": "beam", "label": "Beam search", "kind": "local", "num_beams": 5,
         "note": "Tracks the 5 most probable whole sequences at once and keeps the best, instead of committing to one token at a time. Run locally on the same small model - deterministic, but a base model's beam search often degenerates into repetition, which is itself a well-known real failure mode of beam search, not a bug here."},
    ]

    def _build_chat_messages(self, message, history=None, context=None):
        messages = [{"role": "system", "content": CHAT_SYSTEM}]
        if context:
            messages.append({"role": "system", "content":
                "Reference material for this reply:\n\n" + context})
        for item in (history or [])[-20:]:
            role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        return messages

    @staticmethod
    def _friendly_error(exc):
        # _complete already retries a 429 with backoff several times before giving up -
        # reaching here means the provider stayed saturated through all of them, which
        # is still a transient "try again shortly" state, not a real failure. Worth its
        # own message since the raw httpx exception text ("Client error '429 Too Many
        # Requests' for url ...") reads like something is broken rather than "busy."
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            return "(the AI provider is rate-limited right now - try again in a few seconds)"
        return f"(generation failed: {exc})"

    def generate_variant(self, message, preset, history=None, context=None):
        # One sampling preset, one call - kept separate from generate_variants (below) so
        # the API route can fire all presets through asyncio.to_thread concurrently rather
        # than one after another, which would otherwise take ~4x as long as a normal reply.
        # Skips the self-verification pass chat() normally runs on a grounded answer - the
        # point here is to show each strategy's raw, uncorrected behavior side by side
        # (including where high-temperature sampling drifts from the grounded facts), not
        # to smooth every variant back to the same safe answer.
        messages = self._build_chat_messages(message, history, context)
        try:
            text = self._complete(
                self.model, messages,
                temperature=preset["temperature"], top_p=preset["top_p"],
                max_tokens=500, timeout=60,
            )
        except Exception as exc:
            text = self._friendly_error(exc)
        return {**preset, "text": text}

    @staticmethod
    def _local_seed(message, context=None):
        # top_k/beam presets: distilgpt2 is a base (non-instruction-tuned) model, so it
        # doesn't "answer" a question the way the cloud models do - it continues
        # whatever text it's given. Framing the input as a short completion prompt gets
        # something topically anchored rather than a totally unrelated continuation,
        # though output quality is still well below the cloud presets by design (see the
        # preset notes above) - this is about running the real algorithm, not winning on
        # quality.
        return (f"{context}\n\n" if context else "") + f"Question: {message}\nAnswer:"

    def generate_local_candidates(self, message, preset, context=None, n=5):
        # The `n` candidates distilgpt2 itself actually considered for this preset,
        # ranked by its own real log-probability (see app/eval/metrics.py) - not a
        # proxy, since this is the exact model that generated them.
        from app.eval import metrics
        seed = self._local_seed(message, context)
        try:
            if preset["key"] == "top_k":
                return metrics.generate_topk_candidates(seed, k=preset["top_k"], n=n)
            return metrics.generate_beam_candidates(seed, num_beams=preset["num_beams"], n=n)
        except Exception as exc:
            return [{"text": f"(generation failed: {exc})", "score": None}]

    def _verify_grounded(self, context, question, answer):
        # A narrow yes/no check ("is every specific fact in this draft actually present in
        # the reference text?") is a task models handle far more reliably than open-ended
        # generation - it's classification, not invention. Uses the fast/classifier model
        # (cheap) rather than the main writer model.
        try:
            raw = self._complete(
                self.fast_model,
                [
                    {"role": "system", "content":
                        'Fact-check a draft answer against a reference text. Reply with only a JSON '
                        'object {"relevant": true or false, "supported": true or false}. "relevant" '
                        'is true only if the reference text is actually about the same person, place, '
                        'or thing the question is asking about (not a different entity that happens '
                        'to share a name or spelling - e.g. a question about a company called "X" and '
                        'a reference text about the letter "X" are NOT relevant). "supported" is true '
                        'only if every specific name, date, number, title, or other concrete fact '
                        'stated in the draft answer is explicitly written in the reference text. If '
                        'the draft states a specific fact that the reference text never mentions - '
                        'even one that sounds plausible or well-known - "supported" must be false. '
                        'General, non-specific statements (e.g. restating the question\'s own topic) '
                        'do not need to be checked. If "relevant" is false, "supported" must also be '
                        'false.'},
                    {"role": "user", "content":
                        f"Reference text:\n{context}\n\nQuestion: {question}\n\nDraft answer: {answer}"}
                ],
                temperature=0.0, max_tokens=40, json_mode=True, timeout=30,
            )
            data = json.loads(raw or "{}")
            return {"supported": bool(data.get("supported")), "relevant": bool(data.get("relevant"))}
        except Exception:
            # The verifier itself failing is not a reason to block an otherwise-fine
            # reply - fail open rather than degrade every grounded answer to the fallback.
            return {"supported": True, "relevant": True}

    _CODE_FORMATS = {"py", "js", "ts", "html", "css", "java", "c", "cpp", "sh", "yaml", "json", "xml"}

    # "Write an essay about my dog" has no real dog to describe, so the model invents one
    # (a name, a breed, an anecdote) rather than writing generally about dogs - WRITER_SYSTEM
    # already forbids this, but that rule sits in a long system prompt the model reliably
    # ignores for exactly this case. Repeating it right next to the instruction itself (the
    # text the model just finished reading, not a block from several messages back) catches
    # what the system prompt alone did not; verified against "write an essay about my dog"
    # specifically inventing "Max, a golden retriever" without this reminder.
    _PERSONAL_NO_DETAIL = re.compile(
        r"\bmy\s+(?:dog|cat|pet|puppy|kitten|trip|vacation|car|school|family|friend|city|"
        r"hometown|room|house|job|life|brother|sister|mother|father|parents|girlfriend|"
        r"boyfriend|wife|husband|teacher|neighborhood)\b",
        re.IGNORECASE,
    )

    # A job/internship application letter has the same fabrication risk as "my dog" but in
    # a more consequential direction: asked to make the sender sound qualified, a capable
    # model readily invents specific, checkable résumé claims (a project, a user count, a
    # percentage improvement) to fill the gap - confirmed against "write an email to a
    # hiring manager applying for a software engineering internship", which invented "a
    # REST API used by 2,000+ users" and "reducing response time by 35%" out of nothing,
    # even with WRITER_SYSTEM's bracketed-placeholder rule already covering this case. This
    # request can land in either generate_text (write_document) or chat (general) depending
    # on how the classifier routes it, so both call sites need the same reminder.
    _APPLICATION_LETTER = re.compile(
        r"\b(hiring manager|cover letter|job application|internship application|recruiter|"
        r"apply(?:ing)?\s+for\s+(?:a\s+|an\s+)?(?:job|internship|position|role))\b",
        re.IGNORECASE,
    )
    _FABRICATION_REMINDER = (
        "\n\n(Reminder: do not invent specific achievements, projects, metrics, user counts, "
        "or percentages that weren't given - those are checkable factual claims, not filler. "
        "Use a bracketed placeholder like [a specific achievement, e.g. built X / improved Y "
        "by N%] instead.)"
    )

    def _prepare_document_messages(self, instruction, fmt, context=None):
        # Even a frontier model readily drifts into a chatty reply (greeting, "feel free to
        # ask!", a fabricated persona addressed as "you") instead of writing the actual
        # document, especially on a short, detail-free prompt like "an essay about my dog"
        # - there's no real dog to describe, so it can invent one and reply as if
        # continuing a conversation. The system prompt has to rule that out directly.
        is_code = fmt in self._CODE_FORMATS
        system = WRITER_CODE_SYSTEM if is_code else WRITER_SYSTEM
        user_content = instruction
        if not is_code and not context and self._PERSONAL_NO_DETAIL.search(instruction):
            user_content += (
                "\n\n(Reminder: no specific name, breed, or personal detail was given for "
                "this - do not invent one. Write generally about the topic itself.)"
            )
        if not is_code and self._APPLICATION_LETTER.search(instruction):
            user_content += self._FABRICATION_REMINDER
        if context:
            system += (
                "\n\nSource document(s) are given below the task, each between triple quotes. Base "
                "your output accurately on them: preserve their real facts and structure, and only "
                "change what the task asks you to change (e.g. summarizing, rewriting, expanding, "
                "removing a section). Do not invent content that isn't in the source unless the task "
                "explicitly asks for new original material."
            )
            user_content = f"{context}\n\nTask: {instruction}"
        return system, user_content, is_code

    def generate_text(self, instruction, fmt="docx", context=None):
        system, user_content, is_code = self._prepare_document_messages(instruction, fmt, context)
        text = self._complete(
            self.model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content}
            ],
            temperature=0.4, max_tokens=1800, timeout=120,
        )
        return self._strip_code_fence(text) if is_code else text

    def generate_document_variant(self, instruction, fmt, preset, context=None):
        # Document-writing counterpart to generate_variant() - same cloud presets, but
        # built on WRITER_SYSTEM (plus its fabrication-reminder handling) instead of
        # CHAT_SYSTEM, since a document request is a different kind of prompt than a
        # conversational one. Cloud presets only (greedy/low-temp/nucleus/high-temp) - 
        # top_k/beam always go through generate_document_local_candidates instead, which
        # is the only path that can return real per-candidate probabilities for them.
        system, user_content, is_code = self._prepare_document_messages(instruction, fmt, context)
        try:
            text = self._complete(
                self.model,
                [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
                temperature=preset["temperature"], top_p=preset["top_p"],
                max_tokens=1800, timeout=120,
            )
            if is_code:
                text = self._strip_code_fence(text)
        except Exception as exc:
            text = self._friendly_error(exc)
        return {**preset, "text": text}

    def generate_document_local_candidates(self, instruction, fmt, preset, context=None, n=5):
        _, _, is_code = self._prepare_document_messages(instruction, fmt, context)
        if is_code:
            return []  # distilgpt2 is not a code model; not worth 5 garbage candidates
        from app.eval import metrics
        # Ending the seed on a blank line (as this used to) invites a base model to just
        # keep "continuing" with more blank lines - beam search in particular, since
        # whitespace after whitespace can score as a perfectly plausible top sequence,
        # decoding to an empty/invisible candidate after .strip(). Anchoring on a label
        # word (matching the "Question: ...\nAnswer:" shape _local_seed already uses
        # successfully for chat) gives the model something concrete to continue from.
        seed = (f"{context}\n\n" if context else "") + f"Task: {instruction}\nDraft:"
        try:
            if preset["key"] == "top_k":
                return metrics.generate_topk_candidates(seed, k=preset["top_k"], n=n)
            return metrics.generate_beam_candidates(seed, num_beams=preset["num_beams"], n=n)
        except Exception as exc:
            return [{"text": f"(generation failed: {exc})", "score": None}]

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
        m = re.search(r"(?i)^(?:generate|draw|create|make)\s+(?:an?|some)\s+(?:image|picture|photo|drawing|illustration)\s+(?:of|showing)?\s*(.+)", s)
        if m:
            return {"action":"generate_image","content":m.group(1).strip(" .!")}
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
            "The AI API isn't reachable right now - check that OPENAI_API_KEY is set in the backend's .env file, or try a supported command such as 'Take a note: …'."}

agent = LocalAgent()

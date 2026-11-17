import asyncio, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from app.services.agent import agent, LocalAgent
from app.tools.productivity import create_note, create_reminder, search_files
from app.tools.desktop import open_app, play_music, open_url, run_system_command
from app.tools.files import create_document
from app.tools.imaging import generate_image
from app.tools.knowledge import looks_factual, wikipedia_summary, extract_document_topic, lookup_topic
from app.core.database import save_task
from app.core.variants import generate_all_variants, generate_all_document_variants

TASKS = {}
ALLOWED_DOC_FORMATS = {"docx", "txt", "md", "csv", "json", "py", "js", "ts", "html", "css", "java", "c", "cpp", "sh", "yaml", "xml"}

def _slug(s):
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", s.strip().lower()).strip("_")[:55] or "aether_file"

def _persist(task):
    try:
        save_task(task)
    except Exception:
        pass

def _new_task(instruction):
    task = {"task_id":str(uuid.uuid4()),"instruction":instruction,"status":"queued",
      "message":"Task queued.","steps":[{"name":"Understand command","status":"pending","detail":""},
      {"name":"Execute selected tool","status":"pending","detail":""},
      {"name":"Verify result","status":"pending","detail":""}],
      "output_path":None,"download_url":None,"result":None,"error":None,
      "variants":None,"chosen_variant":None,"_pending":None,
      "created_at":datetime.now(timezone.utc).isoformat()}
    TASKS[task["task_id"]] = task
    _persist(task)
    return task

_UP_WORDS = r"(?:increase|inc|raise|boost|turn\s*up|up|more|max(?:imum)?|full)"
_DOWN_WORDS = r"(?:decrease|dec|lower|reduce|turn\s*down|down|less|dim|min(?:imum)?)"
_SET_WORDS = r"(?:set|change)"

def _parse_system_command(instruction):
    # A tiny classifier model is unreliable at exactly this kind of thing — picking the
    # right one of several similar numeric system controls and pulling out a percentage —
    # so these are matched directly against the raw text instead of trusting its JSON
    # output. This is what caught "decrease brightness" being misrouted as a volume
    # command: "brightness" was never in the model's limited command vocabulary at all.
    low = instruction.lower()
    pct = re.search(r"(\d{1,3})\s*%", instruction)
    amount = min(100, int(pct.group(1))) if pct else None

    for subject, up_cmd, down_cmd, set_cmd in (
        ("volume", "volume_up", "volume_down", "volume_set"),
        ("brightness", "brightness_up", "brightness_down", "brightness_set"),
    ):
        if not re.search(rf"\b{subject}\b", low):
            continue
        if re.search(rf"\b{_SET_WORDS}\b", low) and amount is not None:
            return set_cmd, amount
        if re.search(rf"\b{_DOWN_WORDS}\b", low):
            return down_cmd, amount
        if re.search(rf"\b{_UP_WORDS}\b", low):
            return up_cmd, amount

    if re.search(r"\bmute\b", low):
        return "mute", None
    if re.search(r"\block\b", low):
        return "lock", None
    if re.search(r"\bsleep\b", low):
        return "sleep", None
    if re.search(r"\bscreenshot\b", low):
        return "screenshot", None
    if re.search(r"\bwi[\s-]?fi\b", low):
        if re.search(r"\b(on|enable|connect|turn\s*on)\b", low):
            return "wifi_on", None
        if re.search(r"\b(off|disable|disconnect|turn\s*off)\b", low):
            return "wifi_off", None
    return None, None

def _build_context(attachments):
    if not attachments:
        return None
    parts = []
    for a in attachments:
        name = (a.get("name") or "file").strip() or "file"
        text = (a.get("text") or "").strip()
        if text:
            parts.append(f'Attached file "{name}":\n"""\n{text}\n"""')
    return "\n\n".join(parts) if parts else None

async def create_and_run(instruction, history=None, attachments=None):
    task = _new_task(instruction)
    asyncio.create_task(_run(task, history or [], attachments or []))
    return task

async def _run(task, history=None, attachments=None):
    history = history or []
    context = _build_context(attachments)
    task["status"]="running"; _persist(task)
    try:
        task["steps"][0].update(status="running",detail="Interpreting your instruction with the AI model.")
        plan = await asyncio.to_thread(agent.understand, task["instruction"], history)
        action = plan.get("action","general")
        sys_command, sys_amount = _parse_system_command(task["instruction"])
        if sys_command:
            # Overrides whatever the classifier picked — a direct regex match on "volume"/
            # "brightness"/"mute"/etc. in the user's own words is strictly more trustworthy
            # than the small model's guess for this fixed, unambiguous set of commands.
            action = "system_control"
        task["steps"][0].update(status="completed",detail=f"Selected action: {action}."); _persist(task)
        task["steps"][1].update(status="running",detail="Executing a controlled local tool."); _persist(task)
        if action == "take_note":
            result = await asyncio.to_thread(create_note, plan.get("content") or task["instruction"], plan.get("title") or "Quick note")
            task["output_path"] = result["path"]
        elif action == "set_reminder":
            mins = int(plan.get("minutes") or 0)
            if mins < 1: raise ValueError("Please specify a reminder delay, e.g. 'Remind me in 15 minutes to take a break'.")
            result = create_reminder(plan.get("content") or task["instruction"], mins)
        elif action == "open_app":
            result = await asyncio.to_thread(open_app, plan.get("app") or "")
        elif action == "play_music":
            # The classifier model sometimes drops the song/artist into "query" as an
            # empty string on an unusual phrasing (e.g. "on spotify play X") — fall back
            # to pulling it straight out of the raw instruction so a request never
            # silently degrades into "opened the app with no search at all".
            query = (plan.get("query") or "").strip()
            if not query:
                query = re.sub(
                    r"(?i)\b(on\s+(spotify|youtube|youtube music)|play|put on|listen to|please|some|song|music)\b",
                    "", task["instruction"]
                ).strip(" .,!\"'")
            service = "spotify" if re.search(r"(?i)\bspotify\b", task["instruction"]) else "youtube"
            result = await asyncio.to_thread(play_music, query, service)
        elif action == "search_files":
            result = await asyncio.to_thread(search_files, plan.get("query") or "")
        elif action == "open_website":
            result = await asyncio.to_thread(open_url, plan.get("url") or "")
        elif action == "system_control":
            command = sys_command or plan.get("command") or ""
            result = await asyncio.to_thread(run_system_command, command, sys_amount)
        elif action == "ask_chatgpt":
            from app.tools.browser import browser
            prompt_text = plan.get("content") or task["instruction"]
            response_text = await browser.submit_chatgpt_prompt(prompt_text)
            result = {"message": "Got a response from ChatGPT in the visible browser.", "response": response_text}
        elif action == "generate_image":
            # Deterministic, not generative-text: there's no sampling strategy to
            # compare here (this calls an image API directly, not the LLM), so it
            # doesn't go through the variant-picker flow the way chat/write_document do.
            if not plan.get("content"):
                raise ValueError("Please describe the image you want.")
            path = await asyncio.to_thread(generate_image, plan["content"])
            task["output_path"] = str(path)
            result = {"path": str(path), "message": "Image generated and saved. You can view it below."}
        elif action == "write_document":
            if not plan.get("content"):
                raise ValueError("Please describe what the document should contain.")
            fmt = plan.get("format") if plan.get("format") in ALLOWED_DOC_FORMATS else "docx"
            doc_context = context
            if not doc_context and fmt not in LocalAgent._CODE_FORMATS:
                # Same grounding as a factual chat reply, applied to document writing: an
                # essay/report prompt names its topic after "about"/"on" rather than
                # asking a question, so it needs its own extraction before the same
                # keyless lookup can ground it in real facts instead of invented ones.
                topic = extract_document_topic(plan["content"])
                if topic:
                    doc_context = await asyncio.to_thread(lookup_topic, topic)
            # A classifier that skips "title" shouldn't make every untitled document land
            # on the same generic filename — falling back to words from the request itself
            # (still deduplicated by create_document/safe_output_path as a second layer)
            # keeps unrelated documents from colliding under one name in the first place.
            fallback_title = " ".join(plan["content"].split()[:8])
            variants = await generate_all_document_variants(plan["content"], fmt, doc_context)
            if not any(v["text"] and not v["text"].startswith("(generation failed") for v in variants):
                raise RuntimeError("The AI model returned an empty document.")
            task["variants"] = variants
            task["_pending"] = {"kind": "write_document", "fmt": fmt, "title": plan.get("title") or fallback_title}
            await _await_selection(task)
            return
        elif action == "general":
            # A small local model has no real knowledge of its own and will confidently
            # state wrong specifics for a factual question (wrong founding year, wrong
            # city, an invented accreditation body) rather than admit uncertainty. A
            # quick, keyless Wikipedia lookup grounds the answer in something real —
            # cheap enough (under a couple seconds) not to cost the speed a bigger local
            # model would. Skipped when the user already attached their own document,
            # since that's the more authoritative source for the question.
            chat_context = context
            if not chat_context and looks_factual(task["instruction"]):
                chat_context = await asyncio.to_thread(wikipedia_summary, task["instruction"])
            variants = await generate_all_variants(task["instruction"], history, chat_context)
            task["variants"] = variants
            task["_pending"] = {"kind": "general"}
            await _await_selection(task)
            return
        else:
            result = {"message":plan.get("response") or "I understood your request, but no action was needed."}
        if isinstance(result, dict) and result.get("path") and not task.get("output_path"):
            task["output_path"] = result["path"]
        if task.get("output_path"):
            task["download_url"] = f"/files/{Path(task['output_path']).name}"
        task["result"] = result
        task["steps"][1].update(status="completed",detail=str(result)[:350]); _persist(task)
        task["steps"][2].update(status="running",detail="Checking the action result."); _persist(task)
        if task.get("output_path") and not Path(task["output_path"]).exists():
            raise RuntimeError("The output file could not be verified.")
        task["steps"][2].update(status="completed",detail="Action result verified.")
        task["status"]="completed"; task["message"]=result.get("message") or "Done."
    except Exception as exc:
        task["status"]="failed"; task["error"]=str(exc); task["message"]=f"Could not complete task: {exc}"
        for step in task["steps"]:
            if step["status"] == "running":
                step.update(status="failed",detail=str(exc))
    _persist(task)

async def _await_selection(task):
    # A chat reply or document is generative text with a real choice of sampling
    # strategy behind it — unlike a tool action (open an app, set a reminder), there's
    # something genuine to compare, so these two actions pause here instead of
    # auto-picking one variant, matching the Playground's "show everything, you choose"
    # behavior rather than silently deciding for the user every time.
    task["steps"][1].update(status="completed",detail=f"Generated {len(task['variants'])} variants."); _persist(task)
    task["status"]="awaiting_selection"; task["message"]="Choose a response below."
    _persist(task)

async def select_variant(task_id, variant_key):
    task = TASKS.get(task_id)
    if not task:
        raise KeyError("Task not found.")
    if task["status"] != "awaiting_selection":
        raise ValueError("This task isn't waiting on a selection.")
    variant = next((v for v in task["variants"] if v["key"] == variant_key), None)
    if not variant:
        raise ValueError("Unknown variant.")
    pending = task["_pending"]
    try:
        task["steps"][2].update(status="running",detail="Finalizing your chosen response."); _persist(task)
        if pending["kind"] == "write_document":
            fmt = pending["fmt"]
            path = await asyncio.to_thread(create_document, variant["text"], _slug(pending["title"])+"."+fmt, fmt)
            task["output_path"] = str(path)
            task["download_url"] = f"/files/{Path(path).name}"
            result = {"path": str(path), "message": "Document generated and saved. You can download it below."}
        else:
            result = {"message": variant["text"]}
        task["result"] = result
        task["chosen_variant"] = variant_key
        if task.get("output_path") and not Path(task["output_path"]).exists():
            raise RuntimeError("The output file could not be verified.")
        task["steps"][2].update(status="completed",detail="Action result verified.")
        task["status"] = "completed"
        task["message"] = result.get("message") or "Done."
    except Exception as exc:
        task["status"]="failed"; task["error"]=str(exc); task["message"]=f"Could not complete task: {exc}"
        task["steps"][2].update(status="failed",detail=str(exc))
    _persist(task)
    return task

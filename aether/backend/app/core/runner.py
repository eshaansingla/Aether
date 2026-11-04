import asyncio, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from app.services.agent import agent
from app.tools.productivity import create_note, create_reminder, search_files
from app.tools.desktop import open_app, play_music, open_url, run_system_command
from app.tools.files import create_document
from app.core.database import save_task

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
      "output_path":None,"download_url":None,"result":None,"error":None,"created_at":datetime.now(timezone.utc).isoformat()}
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
        task["steps"][0].update(status="running",detail="Interpreting your instruction with the local language model.")
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
        elif action == "write_document":
            if not plan.get("content"):
                raise ValueError("Please describe what the document should contain.")
            fmt = plan.get("format") if plan.get("format") in ALLOWED_DOC_FORMATS else "docx"
            content = await asyncio.to_thread(agent.generate_text, plan["content"], fmt, context)
            if not content:
                raise RuntimeError("The local model returned an empty document.")
            path = await asyncio.to_thread(create_document, content, _slug(plan.get("title") or "aether_document")+"."+fmt, fmt)
            task["output_path"] = str(path)
            result = {"path":str(path),"message":"Document generated by the local model and saved. You can download it below."}
        elif action == "general":
            reply = await asyncio.to_thread(agent.chat, task["instruction"], history, context)
            result = {"message": reply}
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

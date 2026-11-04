from pathlib import Path
from datetime import datetime, timedelta
import json, re, uuid
from apscheduler.schedulers.background import BackgroundScheduler
from app.config import NOTES_DIR, DATA_DIR

_scheduler = BackgroundScheduler(daemon=True)
_reminders_file = DATA_DIR / "reminders.json"
_reminders = []

def start_scheduler():
    if not _scheduler.running:
        _scheduler.start()
    if _reminders_file.exists():
        try:
            saved = json.loads(_reminders_file.read_text(encoding="utf-8"))
            _reminders.extend(saved)
            for item in saved:
                when = datetime.fromisoformat(item["when"])
                if when > datetime.now() and item.get("status") == "scheduled":
                    _schedule(item)
        except Exception:
            pass

def _persist():
    _reminders_file.write_text(json.dumps(_reminders, indent=2), encoding="utf-8")

def _notify(message):
    # Notifications are surfaced through the API reminder list; desktop polling displays them.
    for item in _reminders:
        if item.get("message") == message and item.get("status") == "scheduled":
            item["status"] = "due"
    _persist()

def _schedule(item):
    _scheduler.add_job(_notify, "date", run_date=datetime.fromisoformat(item["when"]),
                       args=[item["message"]], id=item["id"], replace_existing=True)

def create_note(text: str, title: str = "Quick note"):
    clean = re.sub(r"[^a-zA-Z0-9 _-]", "", title).strip()[:70] or "Quick note"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = NOTES_DIR / f"{stamp}_{clean.replace(' ', '_')}.md"
    path.write_text(f"# {clean}\n\n{text.strip()}\n", encoding="utf-8")
    return {"title": clean, "path": str(path), "content": text.strip()}

def list_notes():
    return [{"name": p.name, "path": str(p), "modified": p.stat().st_mtime}
            for p in sorted(NOTES_DIR.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)]

def _note_path(name: str) -> Path:
    # Path(name).name strips any directory component (including "..") so a crafted
    # name can never escape NOTES_DIR; only an existing .md file in it is ever touched.
    path = NOTES_DIR / Path(name).name
    if path.suffix != ".md" or not path.is_file():
        raise FileNotFoundError(name)
    return path

def get_note(name: str):
    path = _note_path(name)
    return {"name": path.name, "path": str(path), "content": path.read_text(encoding="utf-8")}

def update_note(name: str, content: str):
    path = _note_path(name)
    path.write_text(content, encoding="utf-8")
    return {"name": path.name, "path": str(path), "content": content}

def delete_note(name: str):
    path = _note_path(name)
    path.unlink()

def search_files(query: str, limit: int = 20):
    roots = [Path.home() / "Desktop", Path.home() / "Documents", Path.home() / "Downloads"]
    q = query.lower()
    matches = []
    for base in roots:
        if not base.exists():
            continue
        try:
            for p in base.rglob("*"):
                if p.is_file() and q in p.name.lower():
                    matches.append({"name": p.name, "path": str(p)})
                    if len(matches) >= limit:
                        return matches
        except (PermissionError, OSError):
            continue
    return matches

def create_reminder(message: str, minutes: int):
    if minutes < 1 or minutes > 60 * 24 * 30:
        raise ValueError("Reminder must be between 1 minute and 30 days.")
    item = {"id": str(uuid.uuid4()), "message": message.strip(),
            "when": (datetime.now() + timedelta(minutes=minutes)).isoformat(),
            "status": "scheduled"}
    _reminders.append(item)
    _persist()
    if _scheduler.running:
        _schedule(item)
    return item

def list_reminders():
    return list(reversed(_reminders[-30:]))

def _find_reminder(reminder_id: str):
    for item in _reminders:
        if item["id"] == reminder_id:
            return item
    raise KeyError(reminder_id)

def update_reminder(reminder_id: str, message: str = None, minutes: int = None, status: str = None):
    item = _find_reminder(reminder_id)
    if message is not None:
        item["message"] = message.strip()
    if minutes is not None:
        if minutes < 1 or minutes > 60 * 24 * 30:
            raise ValueError("Reminder must be between 1 minute and 30 days.")
        item["when"] = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        item["status"] = "scheduled"
    if status is not None:
        item["status"] = status
    _persist()
    if _scheduler.running:
        try:
            _scheduler.remove_job(item["id"])
        except Exception:
            pass
        if item["status"] == "scheduled":
            _schedule(item)
    return item

def delete_reminder(reminder_id: str):
    item = _find_reminder(reminder_id)
    _reminders.remove(item)
    _persist()
    if _scheduler.running:
        try:
            _scheduler.remove_job(reminder_id)
        except Exception:
            pass

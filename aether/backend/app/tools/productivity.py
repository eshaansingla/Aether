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

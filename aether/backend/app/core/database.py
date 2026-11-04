import json, sqlite3
from pathlib import Path
from app.config import DB_PATH

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize():
    with connect() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, instruction TEXT NOT NULL, status TEXT NOT NULL,
                message TEXT NOT NULL, output_path TEXT, error TEXT, result_json TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        ''')
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "result_json" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN result_json TEXT")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS task_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                name TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            )
        ''')

def save_task(task):
    with connect() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO tasks
            (task_id,instruction,status,message,output_path,error,result_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,datetime('now'))
        ''', (task["task_id"],task["instruction"],task["status"],task["message"],
              task.get("output_path"),task.get("error"),
              json.dumps(task.get("result"), ensure_ascii=False) if task.get("result") is not None else None,
              task["created_at"]))
        conn.execute("DELETE FROM task_steps WHERE task_id = ?", (task["task_id"],))
        for step in task.get("steps", []):
            conn.execute("INSERT INTO task_steps (task_id,name,status,detail) VALUES (?,?,?,?)",
                         (task["task_id"],step["name"],step["status"],step.get("detail","")))

def get_task(task_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row: return None
        steps = conn.execute("SELECT name,status,detail FROM task_steps WHERE task_id=? ORDER BY id",(task_id,)).fetchall()
        result = dict(row)
        result["steps"] = [dict(s) for s in steps]
        result["result"] = json.loads(result.pop("result_json")) if result.get("result_json") else None
        result["download_url"] = f"/files/{Path(result['output_path']).name}" if result.get("output_path") else None
        return result

def list_tasks(limit=30):
    with connect() as conn:
        rows = conn.execute("SELECT task_id FROM tasks ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    return [get_task(row["task_id"]) for row in rows]

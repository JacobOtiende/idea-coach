"""SQLite access. One local file; backed up each time the app starts."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class DB:
    def __init__(self, path: Path | str = settings.DB_PATH):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA_PATH.read_text())
        try:  # FTS5 index for Phase 5 memory retrieval
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts "
                "USING fts5(item_type, item_id UNINDEXED, content, tags)"
            )
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    # --- generic helpers ---------------------------------------------------
    def insert(self, table: str, **values) -> int:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        cur = self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))
        self.conn.commit()
        return cur.lastrowid

    def update(self, table: str, row_id: int, **values) -> None:
        sets = ", ".join(f"{k} = ?" for k in values)
        self.conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), row_id))
        self.conn.commit()

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # --- sessions and messages -------------------------------------------
    def new_session(self, mode: str) -> int:
        return self.insert("sessions", mode=mode)

    def add_message(self, session_id: int, role: str, content: str) -> int:
        return self.insert("messages", session_id=session_id, role=role, content=content)

    def messages(self, session_id: int) -> list[dict]:
        return self.all("SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,))

    # --- ideas ----------------------------------------------------------------
    def add_idea(self, title: str, description: str, problem: str = "", assumption_changed: str = "",
                 session_id: int | None = None) -> int:
        return self.insert("ideas", title=title, description=description, problem=problem,
                           assumption_changed=assumption_changed, session_id=session_id)

    def get_idea(self, idea_id: int) -> dict | None:
        return self.one("SELECT * FROM ideas WHERE id = ?", (idea_id,))

    def ideas(self) -> list[dict]:
        return self.all("SELECT * FROM ideas ORDER BY updated_at DESC, id DESC")

    def update_idea(self, idea_id: int, **values) -> None:
        values["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.update("ideas", idea_id, **values)

    # --- runs -----------------------------------------------------------------
    def start_run(self, mode: str, idea_id: int | None = None, session_id: int | None = None) -> int:
        from prompts_loader import prompt_version
        return self.insert("runs", mode=mode, idea_id=idea_id, session_id=session_id,
                           prompt_version=prompt_version())

    def end_run(self, run_id: int, status: str, total_cost: float, duration_s: float,
                search_count: int = 0, verdict: str | None = None, notes: str | None = None) -> None:
        self.update("runs", run_id, status=status, total_cost=round(total_cost, 6),
                    duration_s=round(duration_s, 2), search_count=search_count, verdict=verdict,
                    notes=notes, ended_at=datetime.now().isoformat(timespec="seconds"))

    # --- claims and evidence --------------------------------------------------
    def claims(self, idea_id: int) -> list[dict]:
        return self.all("SELECT * FROM claims WHERE idea_id = ? ORDER BY critical DESC, id", (idea_id,))

    def claims_for_run(self, run_id: int) -> list[dict]:
        return self.all("SELECT * FROM claims WHERE run_id = ? ORDER BY critical DESC, id", (run_id,))

    def evidence_for_claim(self, claim_id: int) -> list[dict]:
        return self.all("SELECT * FROM evidence WHERE claim_id = ? ORDER BY id", (claim_id,))

    def claim_events(self, claim_id: int) -> list[dict]:
        return self.all("SELECT * FROM claim_events WHERE claim_id = ? ORDER BY id", (claim_id,))

    # --- results --------------------------------------------------------------
    def save_stress_result(self, idea_id: int, run_id: int, result: dict) -> int:
        return self.insert("stress_results", idea_id=idea_id, run_id=run_id, result_json=json.dumps(result))

    def stress_results(self, idea_id: int) -> list[dict]:
        rows = self.all("SELECT * FROM stress_results WHERE idea_id = ? ORDER BY id DESC", (idea_id,))
        for r in rows:
            r["result"] = json.loads(r["result_json"])
        return rows


def backup(db_path: Path = settings.DB_PATH, backup_dir: Path = settings.BACKUP_DIR,
           keep: int = settings.BACKUPS_TO_KEEP) -> Path | None:
    """Copy the database to the backup folder and keep the newest `keep` copies."""
    if not Path(db_path).exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"idea_coach_{datetime.now():%Y%m%d_%H%M%S}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    copies = sorted(backup_dir.glob("idea_coach_*.db"))
    for old in copies[:-keep]:
        old.unlink(missing_ok=True)
    return target

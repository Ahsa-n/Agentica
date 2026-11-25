"""
Persistent state (SQLite, stdlib) — approvals, audit log, machine registry.

Interim store until the PostgreSQL data layer lands; the tables are shaped so
they can move across unchanged.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "agentica.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id        TEXT PRIMARY KEY,
    created   REAL NOT NULL,
    expires   REAL NOT NULL,
    session   TEXT,
    tool      TEXT NOT NULL,
    target    TEXT NOT NULL,
    args      TEXT NOT NULL,          -- validated args, exactly what will execute
    risk      TEXT NOT NULL,
    reasons   TEXT NOT NULL,          -- JSON list
    summary   TEXT NOT NULL,
    status    TEXT NOT NULL,          -- pending | approved | denied | expired | executed | failed
    decided   REAL,
    result    TEXT                    -- JSON
);
CREATE TABLE IF NOT EXISTS audit (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    session   TEXT,
    tool      TEXT,
    target    TEXT,
    args      TEXT,
    risk      TEXT,
    decision  TEXT,                   -- ALLOW | CONFIRM | DENY | APPROVED | DECLINED | EXPIRED
    reasons   TEXT,
    outcome   TEXT,                   -- ok | error | pending | declined | expired
    detail    TEXT
);
CREATE TABLE IF NOT EXISTS machines (
    id        TEXT PRIMARY KEY,
    label     TEXT NOT NULL,
    host      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    os        TEXT NOT NULL,          -- windows | linux
    transport TEXT NOT NULL,          -- winrm-https | winrm-http | ssh
    port      INTEGER NOT NULL,
    created   REAL NOT NULL,
    username  TEXT,                   -- password lives in the OS keyring, never here
    os_info   TEXT,                   -- JSON from the last successful connection test
    last_ok   REAL,
    last_error TEXT
);
"""
SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id        TEXT PRIMARY KEY,
    title     TEXT NOT NULL DEFAULT '',
    created   REAL NOT NULL,
    updated   REAL NOT NULL,
    target    TEXT,                   -- machine label, NULL = this PC
    loaded    TEXT NOT NULL DEFAULT '{}'   -- Auto mode: toolset id -> turns left (sticky tools)
);
CREATE TABLE IF NOT EXISTS session_items (   -- finished transcript items (user + agent)
    session   TEXT NOT NULL,
    item_id   TEXT NOT NULL,
    seq       INTEGER NOT NULL,
    item      TEXT NOT NULL,          -- JSON
    PRIMARY KEY (session, item_id)
);
"""
APPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    machine   TEXT,                   -- machine label; NULL = this PC
    process   TEXT,                   -- comma-separated process names
    service   TEXT,                   -- Windows / systemd service name
    port      INTEGER,                -- TCP port that must accept connections
    url       TEXT,                   -- HTTP(S) URL that must answer
    created   REAL NOT NULL
);
"""
APP_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id    TEXT NOT NULL,
    ts        REAL NOT NULL,
    status    TEXT NOT NULL,          -- up | degraded | down | unknown | restarted
    summary   TEXT
);
CREATE INDEX IF NOT EXISTS app_events_app ON app_events (app_id, id);
"""
MACHINE_MIGRATIONS = {"username": "TEXT", "os_info": "TEXT", "last_ok": "REAL", "last_error": "TEXT"}


class Store:
    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.executescript(SESSION_SCHEMA)
        self.db.executescript(APPS_SCHEMA)
        self.db.executescript(APP_EVENTS_SCHEMA)
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(machines)")}
        for col, typ in MACHINE_MIGRATIONS.items():
            if col not in cols:
                self.db.execute(f"ALTER TABLE machines ADD COLUMN {col} {typ}")
        self.lock = threading.Lock()

    def _q(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def _x(self, sql: str, params: tuple = ()) -> int:
        with self.lock:
            return self.db.execute(sql, params).rowcount

    # ---------------- approvals ----------------

    def create_approval(self, *, session, tool, target, args, risk, reasons, summary, ttl_s) -> dict:
        now = time.time()
        rec = {
            "id": uuid.uuid4().hex[:12], "created": now, "expires": now + ttl_s, "session": session,
            "tool": tool, "target": target, "args": json.dumps(args), "risk": risk,
            "reasons": json.dumps(reasons), "summary": summary, "status": "pending",
        }
        cols = ("id", "created", "expires", "session", "tool", "target", "args", "risk", "reasons", "summary", "status")
        self._x(f"INSERT INTO approvals ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                tuple(rec[k] for k in cols))
        return self.get_approval(rec["id"])

    def get_approval(self, approval_id: str) -> dict | None:
        rows = self._q("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        if not rows:
            return None
        r = rows[0]
        r["args"] = json.loads(r["args"])
        r["reasons"] = json.loads(r["reasons"])
        r["result"] = json.loads(r["result"]) if r["result"] else None
        if r["status"] == "pending" and r["expires"] < time.time():
            self.transition(approval_id, "pending", "expired")
            r["status"] = "expired"
        return r

    def transition(self, approval_id: str, frm: str, to: str, result: dict | None = None) -> bool:
        """Atomic status change; returns False if the approval was not in `frm` (e.g. double click)."""
        n = self._x(
            "UPDATE approvals SET status = ?, decided = COALESCE(decided, ?), result = COALESCE(?, result)"
            " WHERE id = ? AND status = ?",
            (to, time.time(), json.dumps(result) if result is not None else None, approval_id, frm),
        )
        return n == 1

    # ---------------- audit ----------------

    def audit(self, *, session=None, tool=None, target=None, args=None, risk=None, decision=None,
              reasons=None, outcome=None, detail=None) -> int:
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO audit (ts, session, tool, target, args, risk, decision, reasons, outcome, detail)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (time.time(), session, tool, target, json.dumps(args) if args is not None else None, risk,
                 decision, json.dumps(reasons or []), outcome, detail),
            )
            return cur.lastrowid

    def audit_outcome(self, row_id: int, outcome: str, detail: str | None = None) -> None:
        self._x("UPDATE audit SET outcome = ?, detail = COALESCE(?, detail) WHERE id = ?", (outcome, detail, row_id))

    def audit_recent(self, limit: int = 100) -> list[dict]:
        rows = self._q("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["args"] = json.loads(r["args"]) if r["args"] else None
            r["reasons"] = json.loads(r["reasons"]) if r["reasons"] else []
        return rows

    # ---------------- machines ----------------

    def add_machine(self, *, label, host, os, transport, port, username=None) -> dict | None:
        mid = uuid.uuid4().hex[:10]
        try:
            self._x("INSERT INTO machines (id, label, host, os, transport, port, created, username) VALUES (?,?,?,?,?,?,?,?)",
                    (mid, label, host, os, transport, port, time.time(), username))
        except sqlite3.IntegrityError:
            return None  # duplicate host
        return self.machine(mid)

    @staticmethod
    def _machine_row(r: dict) -> dict:
        r["os_info"] = json.loads(r["os_info"]) if r.get("os_info") else None
        return r

    def machine(self, mid: str) -> dict | None:
        rows = self._q("SELECT * FROM machines WHERE id = ?", (mid,))
        return self._machine_row(rows[0]) if rows else None

    def machines(self) -> list[dict]:
        return [self._machine_row(r) for r in self._q("SELECT * FROM machines ORDER BY created")]

    def set_machine_username(self, mid: str, username: str | None) -> None:
        self._x("UPDATE machines SET username = ?, last_ok = NULL, last_error = NULL WHERE id = ?", (username, mid))

    def record_test(self, mid: str, ok: bool, info: dict | None = None, error: str | None = None) -> None:
        if ok:
            self._x("UPDATE machines SET os_info = ?, last_ok = ?, last_error = NULL WHERE id = ?",
                    (json.dumps(info), time.time(), mid))
        else:
            self._x("UPDATE machines SET last_error = ?, last_ok = NULL WHERE id = ?", (error, mid))

    def machine_by_name(self, name: str) -> dict | None:
        rows = self._q("SELECT * FROM machines WHERE host = ? COLLATE NOCASE OR label = ? COLLATE NOCASE", (name, name))
        return self._machine_row(rows[0]) if rows else None

    def delete_machine(self, mid: str) -> bool:
        return self._x("DELETE FROM machines WHERE id = ?", (mid,)) == 1

    # ---------------- sessions (chat history lives on the server) ----------------

    @staticmethod
    def _session_row(r: dict) -> dict:
        r["loaded"] = json.loads(r["loaded"] or "{}")
        return r

    def create_session(self, target: str | None = None) -> dict:
        now = time.time()
        sid = uuid.uuid4().hex
        self._x("INSERT INTO sessions (id, title, created, updated, target, loaded) VALUES (?,?,?,?,?,?)",
                (sid, "", now, now, target, "{}"))
        return self.session(sid)

    def session(self, sid: str) -> dict | None:
        rows = self._q("SELECT * FROM sessions WHERE id = ?", (sid,))
        return self._session_row(rows[0]) if rows else None

    def sessions(self, limit: int = 100) -> list[dict]:
        return [self._session_row(r) for r in self._q("SELECT * FROM sessions ORDER BY updated DESC LIMIT ?", (limit,))]

    def update_session(self, sid: str, **fields) -> None:
        allowed = {"title", "target", "loaded", "updated"}
        sets, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(k)
            sets.append(f"{k} = ?")
            vals.append(json.dumps(v) if k == "loaded" else v)
        if "updated" not in fields:
            sets.append("updated = ?")
            vals.append(time.time())
        self._x(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", (*vals, sid))

    def delete_session(self, sid: str) -> bool:
        self._x("DELETE FROM session_items WHERE session = ?", (sid,))
        return self._x("DELETE FROM sessions WHERE id = ?", (sid,)) == 1

    def put_item(self, sid: str, item: dict) -> None:
        """Insert or replace a finished transcript item (idempotent on item['id'])."""
        with self.lock:
            row = self.db.execute("SELECT seq FROM session_items WHERE session = ? AND item_id = ?",
                                  (sid, item["id"])).fetchone()
            seq = row[0] if row else (self.db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM session_items WHERE session = ?",
                                                      (sid,)).fetchone()[0])
            self.db.execute("INSERT OR REPLACE INTO session_items (session, item_id, seq, item) VALUES (?,?,?,?)",
                            (sid, item["id"], seq, json.dumps(item)))

    def items(self, sid: str) -> list[dict]:
        return [json.loads(r["item"]) for r in self._q("SELECT item FROM session_items WHERE session = ? ORDER BY seq", (sid,))]

    # ---------------- applications (status monitoring) ----------------

    APP_FIELDS = ("name", "machine", "process", "service", "port", "url")

    def add_app(self, **f) -> dict | None:
        aid = uuid.uuid4().hex[:10]
        try:
            self._x("INSERT INTO apps (id, name, machine, process, service, port, url, created) VALUES (?,?,?,?,?,?,?,?)",
                    (aid, f["name"], f.get("machine"), f.get("process"), f.get("service"), f.get("port"), f.get("url"), time.time()))
        except sqlite3.IntegrityError:
            return None
        return self.app(aid)

    def update_app(self, aid: str, **f) -> dict | None:
        try:
            self._x("UPDATE apps SET name = ?, machine = ?, process = ?, service = ?, port = ?, url = ? WHERE id = ?",
                    (f["name"], f.get("machine"), f.get("process"), f.get("service"), f.get("port"), f.get("url"), aid))
        except sqlite3.IntegrityError:
            return None
        return self.app(aid)

    def app(self, aid: str) -> dict | None:
        rows = self._q("SELECT * FROM apps WHERE id = ?", (aid,))
        return rows[0] if rows else None

    def apps(self) -> list[dict]:
        return self._q("SELECT * FROM apps ORDER BY name COLLATE NOCASE")

    def delete_app(self, aid: str) -> bool:
        self._x("DELETE FROM app_events WHERE app_id = ?", (aid,))
        return self._x("DELETE FROM apps WHERE id = ?", (aid,)) == 1

    def add_app_event(self, aid: str, status: str, summary: str | None, keep: int = 50) -> None:
        self._x("INSERT INTO app_events (app_id, ts, status, summary) VALUES (?,?,?,?)", (aid, time.time(), status, summary))
        self._x("DELETE FROM app_events WHERE app_id = ? AND id NOT IN "
                "(SELECT id FROM app_events WHERE app_id = ? ORDER BY id DESC LIMIT ?)", (aid, aid, keep))

    def app_events(self, aid: str, limit: int = 10) -> list[dict]:
        return self._q("SELECT ts, status, summary FROM app_events WHERE app_id = ? ORDER BY id DESC LIMIT ?", (aid, limit))

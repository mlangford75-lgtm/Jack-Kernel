"""Jack Agentic's durable, host-owned forensic turn/attempt journal.

Only fingerprints and provenance are recorded; raw user/model contents, native
thinking, tool arguments and results never enter this database. Not a memory
retrieval system or a replacement for the caller's conversation history.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import time
import uuid


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def attempt_id() -> str:
    return "jack-attempt-" + uuid.uuid4().hex


class ForensicConflict(RuntimeError):
    """Rejected ownership, state transition or stale attempt."""


class AgenticForensicJournal:
    """Persistent SQLite transition journal; records cannot synthesize model content."""

    def __init__(self, path=None):
        configured = path or os.environ.get("JACK_AGENTIC_FORENSIC_DB")
        self.path = Path(configured).expanduser() if configured else (
            Path.home() / ".jack_kernel" / "agentic_forensic.sqlite3"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        was_absent = not self.path.exists()
        with self._read() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS turns (
                turn_id TEXT PRIMARY KEY,
                request_sha256 TEXT NOT NULL,
                stage1_attempt TEXT NOT NULL,
                stage2_attempt TEXT,
                status TEXT NOT NULL,
                a1_sha256 TEXT,
                memory_sha256 TEXT,
                tool_sha256 TEXT,
                wire_sha256 TEXT,
                memory_chars INTEGER,
                receipt_chars INTEGER,
                answer_chars INTEGER,
                failure TEXT,
                created REAL NOT NULL,
                updated REAL NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id TEXT NOT NULL,
                attempt TEXT NOT NULL,
                status TEXT NOT NULL,
                fingerprint TEXT,
                created REAL NOT NULL,
                FOREIGN KEY(turn_id) REFERENCES turns(turn_id)
                )"""
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS turn_artifact_pair ON "
                "turns(request_sha256,wire_sha256)"
            )
        if was_absent and os.name != "nt":
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _read(self):
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _write(self):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _get(db, key):
        return db.execute("SELECT * FROM turns WHERE turn_id=?", (key,)).fetchone()

    @staticmethod
    def _event(db, key, attempt, status, fingerprint=None):
        db.execute(
            "INSERT INTO events(turn_id,attempt,status,fingerprint,created) "
            "VALUES(?,?,?,?,?)", (key, attempt, status, fingerprint, time.time()),
        )

    @staticmethod
    def _check(condition, detail):
        if not condition:
            raise ForensicConflict(detail)

    def begin(self, turn_id, request_hash, a1_attempt):
        self._check(
            turn_id.startswith("jack-turn-") and len(request_hash) == 64
            and a1_attempt.startswith("jack-attempt-"),
            "invalid forensic identity",
        )
        with self._write() as db:
            old = self._get(db, turn_id)
            if old is not None:
                self._check(
                    old["request_sha256"] == request_hash
                    and old["stage1_attempt"] == a1_attempt
                    and old["status"] in ("stage1_active", "awaiting_tool"),
                    "stale attempt or conflicting request owner",
                )
                if old["status"] == "awaiting_tool":
                    db.execute(
                        "UPDATE turns SET status='stage1_active',updated=? WHERE turn_id=?",
                        (time.time(), turn_id),
                    )
                    self._event(db, turn_id, a1_attempt, "stage1_active")
                return
            now = time.time()
            db.execute(
                "INSERT INTO turns(turn_id,request_sha256,stage1_attempt,status,"
                "created,updated) VALUES(?,?,?,?,?,?)",
                (turn_id, request_hash, a1_attempt, "stage1_active", now, now),
            )
            self._event(db, turn_id, a1_attempt, "stage1_active", request_hash)

    def awaiting_tool(self, turn_id, a1_attempt):
        with self._write() as db:
            old = self._get(db, turn_id)
            self._check(
                old is not None and old["stage1_attempt"] == a1_attempt
                and old["status"] in ("stage1_active", "awaiting_tool"),
                "unowned tool suspension",
            )
            if old["status"] != "awaiting_tool":
                db.execute(
                    "UPDATE turns SET status='awaiting_tool',updated=? WHERE turn_id=?",
                    (time.time(), turn_id),
                )
                self._event(db, turn_id, a1_attempt, "awaiting_tool")

    def freeze(self, turn_id, a1_attempt, answer):
        self._check(isinstance(answer, str) and bool(answer.strip()),
                    "Stage 1 has no completed answer")
        fingerprint = sha256(answer)
        with self._write() as db:
            old = self._get(db, turn_id)
            self._check(
                old is not None and old["stage1_attempt"] == a1_attempt,
                "Stage 1 cannot claim another attempt",
            )
            if old["status"] == "stage1_frozen":
                self._check(old["a1_sha256"] == fingerprint,
                            "frozen Stage-1 answer cannot be replaced")
                return fingerprint
            self._check(old["status"] in ("stage1_active", "awaiting_tool"),
                        "Stage 1 cannot freeze in current state")
            db.execute(
                "UPDATE turns SET status='stage1_frozen',a1_sha256=?,updated=? "
                "WHERE turn_id=?", (fingerprint, time.time(), turn_id),
            )
            self._event(db, turn_id, a1_attempt, "stage1_frozen", fingerprint)
        return fingerprint

    def stage2(self, turn_id, a1_attempt, a2_attempt, answer_hash):
        with self._write() as db:
            old = self._get(db, turn_id)
            self._check(
                old is not None
                and old["stage1_attempt"] == a1_attempt
                and old["a1_sha256"] == answer_hash,
                "Stage 2 does not own the frozen Stage-1 answer",
            )
            if old["status"] == "stage2_active" and old["stage2_attempt"] == a2_attempt:
                return
            self._check(
                old["status"] in ("stage1_frozen", "memory_failed"),
                "Stage 2 requires an accepted frozen answer",
            )
            self._check(a2_attempt.startswith("jack-attempt-"),
                        "invalid Stage-2 attempt identity")
            db.execute(
                "UPDATE turns SET status='stage2_active',stage2_attempt=?,updated=? "
                "WHERE turn_id=?", (a2_attempt, time.time(), turn_id),
            )
            self._event(db, turn_id, a2_attempt, "stage2_active", answer_hash)

    def commit(self, turn_id, a2_attempt, answer, memory, receipt):
        self._check(isinstance(memory, str) and bool(memory.strip()),
                    "cannot commit an empty Agentic Memory")
        a1_hash = sha256(answer)
        wire = memory + receipt + "\n\n" + answer
        with self._write() as db:
            old = self._get(db, turn_id)
            self._check(
                old is not None and old["status"] == "stage2_active"
                and old["stage2_attempt"] == a2_attempt
                and old["a1_sha256"] == a1_hash,
                "memory does not belong to frozen Stage-1 attempt",
            )
            db.execute(
                "UPDATE turns SET status='complete',memory_sha256=?,tool_sha256=?,"
                "wire_sha256=?,memory_chars=?,receipt_chars=?,answer_chars=?,updated=? "
                "WHERE turn_id=?",
                (sha256(memory), sha256(receipt), sha256(wire), len(memory),
                 len(receipt), len(answer), time.time(), turn_id),
            )
            self._event(db, turn_id, a2_attempt, "complete", sha256(memory))

    def fail(self, turn_id, attempt, reason):
        with self._write() as db:
            old = self._get(db, turn_id)
            if old is None or old["status"] in (
                "complete", "stage1_failed", "memory_failed",
            ):
                return
            if old["status"] in ("stage1_active", "awaiting_tool"):
                self._check(old["stage1_attempt"] == attempt,
                            "wrong Stage-1 attempt cannot fail a turn")
                state = "stage1_failed"
            else:
                self._check(
                    attempt == (old["stage2_attempt"] or old["stage1_attempt"]),
                    "wrong attempt cannot fail Stage 2",
                )
                state = "memory_failed"
            db.execute(
                "UPDATE turns SET status=?,failure=?,updated=? WHERE turn_id=?",
                (state, str(reason)[:256], time.time(), turn_id),
            )
            self._event(db, turn_id, attempt, state)

    def get(self, turn_id):
        with self._read() as db:
            obj = self._get(db, turn_id)
            return dict(obj) if obj is not None else None

    def match_visible(self, request_hash, wire_hash):
        """Resolve only an unambiguous, exact caller-supplied completed U/M/A.

        Neither prompt content nor assistant content is retrieved from this DB.
        """
        with self._read() as db:
            rows = db.execute(
                "SELECT * FROM turns WHERE request_sha256=? AND wire_sha256=? "
                "AND status='complete' LIMIT 2",
                (request_hash, wire_hash),
            ).fetchall()
            return dict(rows[0]) if len(rows) == 1 else None

    def events(self, turn_id):
        with self._read() as db:
            return [dict(x) for x in db.execute(
                "SELECT * FROM events WHERE turn_id=? ORDER BY seq",
                (turn_id,),
            )]

    def retry_stage1(self, turn_id, request_hash, new_attempt):
        """For authenticated host recovery. Never called based on model text."""
        with self._write() as db:
            old = self._get(db, turn_id)
            self._check(
                old is not None and old["status"] == "stage1_failed"
                and old["request_sha256"] == request_hash
                and old["stage1_attempt"] != new_attempt,
                "cannot restart stale or unverified transaction",
            )
            db.execute(
                "UPDATE turns SET stage1_attempt=?,stage2_attempt=NULL,"
                "status='stage1_active',failure=NULL,updated=? WHERE turn_id=?",
                (new_attempt, time.time(), turn_id),
            )
            self._event(db, turn_id, new_attempt, "stage1_active")

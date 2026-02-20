import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GloveDB:
    def __init__(self, path: str):
        self.path = path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approval_requests (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    approved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    request_id TEXT,
                    action TEXT,
                    target TEXT,
                    outcome TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    prev_hash TEXT,
                    entry_hash TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_setting(self, key: str) -> Optional[str]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()

    def set_setting(self, key: str, value: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def create_request(
        self,
        request_id: str,
        action: str,
        target: str,
        metadata: Dict[str, Any],
        risk: str,
        reason: str,
        policy_id: str,
        expires_at: str,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO approval_requests
                (id, action, target, metadata_json, risk, status, reason, policy_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    request_id,
                    action,
                    target,
                    json.dumps(metadata, separators=(",", ":")),
                    risk,
                    reason,
                    policy_id,
                    now_iso(),
                    expires_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM approval_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["metadata"] = json.loads(data.pop("metadata_json"))
            return data
        finally:
            conn.close()

    def increment_attempts(self, request_id: str) -> int:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE approval_requests SET attempts = attempts + 1 WHERE id = ?",
                (request_id,),
            )
            conn.commit()
            row = conn.execute("SELECT attempts FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
            return int(row["attempts"]) if row else 0
        finally:
            conn.close()

    def set_request_status(self, request_id: str, status: str) -> None:
        conn = self._connect()
        try:
            approved_at = now_iso() if status == "approved" else None
            conn.execute(
                "UPDATE approval_requests SET status = ?, approved_at = ? WHERE id = ?",
                (status, approved_at, request_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_pending_requests(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM approval_requests
                WHERE status = 'pending'
                ORDER BY created_at DESC
                LIMIT 100
                """
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                data = dict(row)
                data["metadata"] = json.loads(data.pop("metadata_json"))
                out.append(data)
            return out
        finally:
            conn.close()

    def append_audit(
        self,
        event_type: str,
        outcome: str,
        details: Dict[str, Any],
        request_id: Optional[str] = None,
        action: Optional[str] = None,
        target: Optional[str] = None,
    ) -> None:
        conn = self._connect()
        try:
            prev = conn.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            prev_hash = prev["entry_hash"] if prev else ""
            ts = now_iso()
            payload = json.dumps(details, sort_keys=True, separators=(",", ":"))
            source = f"{prev_hash}|{ts}|{event_type}|{request_id or ''}|{action or ''}|{target or ''}|{outcome}|{payload}"
            entry_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
            conn.execute(
                """
                INSERT INTO audit_log
                (ts, event_type, request_id, action, target, outcome, details_json, prev_hash, entry_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, event_type, request_id, action, target, outcome, payload, prev_hash or None, entry_hash),
            )
            conn.commit()
        finally:
            conn.close()

    def recent_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                data = dict(row)
                data["details"] = json.loads(data.pop("details_json"))
                out.append(data)
            return out
        finally:
            conn.close()

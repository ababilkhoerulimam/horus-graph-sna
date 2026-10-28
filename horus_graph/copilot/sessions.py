"""
Riwayat percakapan copilot, disimpan di memori proses.

Sesi bersifat sementara: hilang saat server berhenti. Itu disengaja, karena isi
percakapan adalah turunan dari bundle yang sedang dimuat, bukan data primer.
Jumlah sesi dibatasi supaya proses berjalan lama tidak tumbuh tanpa batas.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SESSION_DB_ENV = "HORUS_SESSION_DB"
MAX_SESSIONS = 50
MAX_MESSAGES_PER_SESSION = 200
TITLE_MAX_CHARS = 60


@dataclass
class Session:
    id: str
    title: str
    created_at: float
    updated_at: float
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "message_count": len(self.messages),
        }


class SessionStore:
    """
    Riwayat percakapan copilot.

    Tanpa `path`, semuanya di memori dan hilang saat proses berhenti. Dengan
    `path`, setiap perubahan ditulis ke SQLite sehingga restart tidak
    menghilangkan sesi — isi percakapan memang turunan bundle, tetapi
    menghapusnya saat deploy hanya memaksa pengguna mengulang pertanyaan.

    Muat-semuanya-ke-memori dipilih di atas query per panggilan karena
    jumlah sesi dibatasi `MAX_SESSIONS`; satu query per pembacaan hanya
    menambah kode tanpa mengubah perilaku.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._db: Optional[sqlite3.Connection] = None
        if path:
            self._open(path)

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            sessions = sorted(
                self._sessions.values(), key=lambda item: item.updated_at, reverse=True
            )
            return [item.as_dict() for item in sessions]

    def create_session(self, title: Optional[str] = None) -> Dict[str, Any]:
        now = time.time()
        session = Session(
            id=uuid.uuid4().hex,
            title=(title or "Sesi baru").strip()[:TITLE_MAX_CHARS] or "Sesi baru",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._sessions[session.id] = session
            self._write_session(session)
            self._evict()
            return session.as_dict()

    def ensure_session(self, session_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        """
        Pakai id dari klien, buat bila belum ada.

        Drawer menyimpan id sesi di localStorage; mengadopsinya membuat riwayat
        tetap nyambung setelah server dimulai ulang.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                now = time.time()
                session = Session(
                    id=session_id,
                    title=(title or "Sesi baru").strip()[:TITLE_MAX_CHARS] or "Sesi baru",
                    created_at=now,
                    updated_at=now,
                )
                self._sessions[session_id] = session
                self._write_session(session)
                self._evict()
            return session.as_dict()

    def get_session_messages(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            messages = list(session.messages)
        if limit is not None:
            messages = messages[-limit:]
        return messages

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_name: Optional[str] = None,
        canvas_command: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            message = {
                "role": role,
                "content": content,
                "agent_name": agent_name,
                "canvas_command": canvas_command,
                "created_at": _iso(time.time()),
            }
            session.messages.append(message)
            if len(session.messages) > MAX_MESSAGES_PER_SESSION:
                session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]
            session.updated_at = time.time()
            if role == "user" and session.title == "Sesi baru":
                session.title = content.strip()[:TITLE_MAX_CHARS] or "Sesi baru"
            self._write_message(session_id, message)
            self._write_session(session)
            return message

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            removed = self._sessions.pop(session_id, None) is not None
            if removed:
                self._drop(session_id)
            return removed

    def _open(self, path: str) -> None:
        """Siapkan berkas SQLite dan muat isinya ke memori."""
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                agent_name TEXT,
                canvas_command TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        self._db.commit()
        self._load()

    def _load(self) -> None:
        if self._db is None:
            return
        rows = self._db.execute(
            "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at"
        ).fetchall()
        for session_id, title, created_at, updated_at in rows:
            messages = [
                {
                    "role": role,
                    "content": content,
                    "agent_name": agent_name,
                    "canvas_command": json.loads(canvas_command) if canvas_command else None,
                    "created_at": _iso(created_at),
                }
                for role, content, agent_name, canvas_command, created_at in self._db.execute(
                    "SELECT role, content, agent_name, canvas_command, created_at "
                    "FROM messages WHERE session_id = ? ORDER BY seq",
                    (session_id,),
                ).fetchall()
            ]
            self._sessions[session_id] = Session(
                id=session_id,
                title=title,
                created_at=created_at,
                updated_at=updated_at,
                messages=messages,
            )

    def _write_session(self, session: Session) -> None:
        """Tulis satu sesi; dipanggil dengan lock aktif."""
        if self._db is None:
            return
        self._db.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title = excluded.title, updated_at = excluded.updated_at",
            (session.id, session.title, session.created_at, session.updated_at),
        )
        self._db.commit()

    def _write_message(self, session_id: str, message: Dict[str, Any]) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT INTO messages (session_id, role, content, agent_name, canvas_command, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                message["role"],
                message["content"],
                message["agent_name"],
                json.dumps(message["canvas_command"], ensure_ascii=False)
                if message["canvas_command"]
                else None,
                time.time(),
            ),
        )
        self._db.commit()

    def _drop(self, session_id: str) -> None:
        if self._db is None:
            return
        self._db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._db.commit()

    def _evict(self) -> None:
        """Buang sesi terlama bila melewati batas; dipanggil dengan lock aktif."""
        if len(self._sessions) <= MAX_SESSIONS:
            return
        ordered = sorted(self._sessions.values(), key=lambda item: item.updated_at)
        for session in ordered[: len(self._sessions) - MAX_SESSIONS]:
            self._sessions.pop(session.id, None)
            self._drop(session.id)


_store: Optional[SessionStore] = None
_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SessionStore(os.environ.get(SESSION_DB_ENV) or None)
    return _store


def configure_store(path: Optional[str]) -> SessionStore:
    """
    Ganti store proses ini, dipakai tes dan `create_app`.

    Dipisah dari `get_session_store` supaya dua aplikasi dalam satu proses
    tidak saling meminjam riwayat percakapan.
    """
    global _store
    with _store_lock:
        _store = SessionStore(path)
    return _store


def _iso(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

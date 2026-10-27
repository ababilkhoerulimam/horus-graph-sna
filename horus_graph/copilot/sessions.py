"""
Riwayat percakapan copilot, disimpan di memori proses.

Sesi bersifat sementara: hilang saat server berhenti. Itu disengaja, karena isi
percakapan adalah turunan dari bundle yang sedang dimuat, bukan data primer.
Jumlah sesi dibatasi supaya proses berjalan lama tidak tumbuh tanpa batas.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

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
            return message

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _evict(self) -> None:
        """Buang sesi terlama bila melewati batas; dipanggil dengan lock aktif."""
        if len(self._sessions) <= MAX_SESSIONS:
            return
        ordered = sorted(self._sessions.values(), key=lambda item: item.updated_at)
        for session in ordered[: len(self._sessions) - MAX_SESSIONS]:
            self._sessions.pop(session.id, None)


_store: Optional[SessionStore] = None
_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SessionStore()
    return _store


def _iso(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

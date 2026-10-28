"""
Kanal copilot: WebSocket untuk percakapan dan REST untuk riwayat sesi.

Dipisahkan dari `api/routes.py` supaya HTTP pembacaan data tetap bisa dipasang
tanpa WebSocket. Semua handler membaca `AppState` yang sama dengan endpoint
lain, jadi angka di drawer copilot tidak bisa berbeda dari kanvas.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from ..api import audit
from ..api.auth import (
    Identity,
    check_rate,
    origin_matches_host,
    rate_limited,
    require_role,
    require_token,
    websocket_identity,
)
from ..api.state import BundleNotFound, get_state
from ..contract.snapshot import snapshot_id
from .llm import llm_available
from .service import Copilot, get_copilot
from .sessions import get_session_store

logger = logging.getLogger("horus_graph.copilot.ws")

# Dependency dipasang per-route, bukan di router: router ini juga memuat
# endpoint WebSocket, dan `Request` tidak ada di scope WebSocket.
_AUTH = [Depends(require_token)]
router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None


def _copilot(bundle_path: Any) -> Copilot:
    try:
        state = get_state(bundle_path)
    except BundleNotFound as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return get_copilot(str(state.root))


# --- jejak audit ------------------------------------------------------------


def _snapshot_of(bundle_path: Any = None) -> Optional[str]:
    try:
        state = get_state(bundle_path)
    except Exception:  # pragma: no cover - jejak tidak boleh menjatuhkan permintaan
        return None
    manifest = state.bundle.manifest
    return manifest.snapshot_id or snapshot_id(manifest)


def _audit_action(
    who: Identity,
    action: str,
    detail: Optional[Dict[str, Any]] = None,
    bundle_path: Any = None,
) -> bool:
    """Satu baris jejak untuk mutasi yang datang lewat REST."""
    return audit.record(
        audit.audit_path(),
        actor=who.actor,
        role=who.role,
        action=action,
        snapshot=_snapshot_of(bundle_path),
        detail=detail,
    )


class _SocketClosed(Exception):
    """Ditutup dari dalam handler; loop utama harus berhenti, bukan mengirim lagi."""


def _audit_socket(websocket: WebSocket, action: str, detail: Optional[Dict[str, Any]] = None) -> bool:
    """Satu baris jejak untuk mutasi yang datang lewat WebSocket."""
    who = getattr(websocket.state, "identity", None)
    if not isinstance(who, Identity):  # pragma: no cover - handshake selalu mengisi
        return True
    return _audit_action(who, action, detail)


# --- riwayat sesi ----------------------------------------------------------


@router.get("/api/chat/sessions", dependencies=_AUTH)
def list_sessions() -> Dict[str, Any]:
    return {"sessions": get_session_store().list_sessions()}


@router.post("/api/chat/sessions", dependencies=_AUTH + [Depends(rate_limited("chat"))])
def create_session(
    request: Request,
    payload: Optional[CreateSessionRequest] = None,
    who: Identity = Depends(require_role("analyst")),
) -> Dict[str, Any]:
    title = payload.title if payload else None
    dibuat = get_session_store().create_session(title=title)
    _audit_action(
        who, "chat.session.create", {"session_id": dibuat.get("id")}, request.app.state.bundle_path
    )
    return dibuat


@router.get("/api/chat/sessions/{session_id}/messages", dependencies=_AUTH)
def session_messages(session_id: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "messages": get_session_store().get_session_messages(session_id),
    }


@router.delete(
    "/api/chat/sessions/{session_id}",
    dependencies=_AUTH + [Depends(rate_limited("chat"))],
)
def delete_session(
    request: Request,
    session_id: str,
    who: Identity = Depends(require_role("analyst")),
) -> Dict[str, Any]:
    # Menghapus riwayat orang lain mengubah temuan yang mungkin sudah dikutip,
    # jadi perannya sama dengan menghapus catatan.
    if not get_session_store().delete_session(session_id):
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.")
    _audit_action(
        who, "chat.session.delete", {"session_id": session_id}, request.app.state.bundle_path
    )
    return {"status": "deleted", "session_id": session_id}


# --- introspeksi -----------------------------------------------------------


@router.get("/api/copilot/tools", dependencies=_AUTH)
def copilot_tools(request: Request) -> Dict[str, Any]:
    from .tools import tool_names

    return {
        "llm": llm_available(),
        "tools": tool_names(),
        "greeting": _copilot(request.app.state.bundle_path).greeting(),
    }


# --- websocket -------------------------------------------------------------


@router.websocket("/ws/copilot")
async def copilot_socket(websocket: WebSocket) -> None:
    # Diperiksa sebelum `accept()`: handshake yang ditolak tidak boleh menjadi
    # koneksi yang hidup. WebSocket tidak tunduk pada same-origin policy, jadi
    # Origin dan identitas diperiksa di sini, bukan diserahkan ke browser.
    # Aturan identitasnya sama dengan HTTP: gerbang SSO yang menyala menuntut
    # header, dan handshake tanpa identitas ditutup 1008 — bukan diterima
    # sebagai pengguna lokal.
    if not origin_matches_host(websocket):
        await websocket.close(code=1008)
        return
    try:
        websocket.state.identity = websocket_identity(websocket)
    except HTTPException:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        copilot = _copilot(websocket.app.state.bundle_path)
    except HTTPException as exc:
        await websocket.send_json({"type": "AGENT_ERROR", "payload": {"error": exc.detail}})
        await websocket.close()
        return

    summary = copilot.state.network.summary
    await websocket.send_json(
        {
            "type": "SYSTEM_CONNECTED",
            "payload": {
                "message": copilot.greeting(),
                "title": copilot.state.presentation.title,
                "total_nodes": summary.get("nodes"),
                "total_edges": summary.get("edges"),
                "density": summary.get("density"),
                "llm": llm_available(),
            },
        }
    )

    while True:
        try:
            message = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        except Exception as exc:  # noqa: BLE001 - payload rusak tidak boleh memutus sesi
            await websocket.send_json(
                {"type": "AGENT_ERROR", "payload": {"error": f"Pesan tidak valid: {exc}"}}
            )
            continue

        kind = message.get("type", "")
        payload = message.get("payload") or {}

        if kind == "PING":
            await websocket.send_json({"type": "PONG"})

        elif kind == "NODE_SELECTED":
            node_id = str(payload.get("node_id") or "")
            if not node_id:
                continue
            dossier = copilot.dossier(node_id)
            if dossier.get("status") == "ready":
                await websocket.send_json(
                    {"type": "NODE_DOSSIER_READY", "payload": dossier}
                )
            else:
                await websocket.send_json(
                    {
                        "type": "AGENT_ERROR",
                        "payload": {
                            "error": dossier.get("message", f"Profil '{node_id}' tidak tersedia.")
                        },
                    }
                )

        elif kind == "USER_CHAT_QUERY":
            try:
                await _handle_query(websocket, copilot, payload)
            except _SocketClosed:
                return

        elif kind == "TRIGGER_CANVAS_COMMAND":
            await websocket.send_json({"type": "CANVAS_COMMAND", "payload": payload})


async def _handle_query(
    websocket: WebSocket, copilot: Copilot, payload: Dict[str, Any]
) -> None:
    query = str(payload.get("message") or "").strip()
    if not query:
        return

    who = getattr(websocket.state, "identity", None)
    if isinstance(who, Identity) and not check_rate(who, bucket="chat.query", limit=10):
        # Satu pesan memicu panggilan model; batasnya lebih ketat daripada
        # bucket tulis biasa, dan ditutup 1013 (coba lagi nanti) supaya klien
        # tahu ini bukan kesalahan permanen.
        await websocket.send_json(
            {"type": "AGENT_ERROR", "payload": {"error": "Terlalu banyak pertanyaan; coba lagi sebentar."}}
        )
        await websocket.close(code=1013)
        raise _SocketClosed()

    store = get_session_store()
    session_id = payload.get("session_id")
    if session_id:
        store.ensure_session(str(session_id))
        session_id = str(session_id)
    else:
        session_id = store.create_session()["id"]

    store.append_message(session_id=session_id, role="user", content=query)
    # Isi pesan tidak dicatat: yang perlu bisa ditelusuri adalah siapa bertanya
    # dan sesi mana, bukan isi percakapannya.
    _audit_socket(
        websocket,
        "chat.query",
        {"session_id": session_id, "chars": len(query)},
    )
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in store.get_session_messages(session_id, limit=10)[:-1]
    ]

    result = await copilot.answer(query, history=history)

    store.append_message(
        session_id=session_id,
        role="assistant",
        content=result.get("text", ""),
        agent_name=result.get("agent"),
        canvas_command=result.get("canvas_command"),
    )

    await websocket.send_json(
        {
            "type": "AGENT_MESSAGE",
            "payload": {
                "session_id": session_id,
                "agent": result.get("agent", "Copilot"),
                "text": result.get("text", ""),
                "llm": bool(result.get("llm")),
            },
        }
    )

    if result.get("canvas_command"):
        await websocket.send_json(
            {"type": "CANVAS_COMMAND", "payload": result["canvas_command"]}
        )

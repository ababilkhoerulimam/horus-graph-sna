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

from ..api.auth import origin_matches_host, require_token, token_ok, websocket_token
from ..api.state import BundleNotFound, get_state
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


# --- riwayat sesi ----------------------------------------------------------


@router.get("/api/chat/sessions", dependencies=_AUTH)
def list_sessions() -> Dict[str, Any]:
    return {"sessions": get_session_store().list_sessions()}


@router.post("/api/chat/sessions", dependencies=_AUTH)
def create_session(payload: Optional[CreateSessionRequest] = None) -> Dict[str, Any]:
    title = payload.title if payload else None
    return get_session_store().create_session(title=title)


@router.get("/api/chat/sessions/{session_id}/messages", dependencies=_AUTH)
def session_messages(session_id: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "messages": get_session_store().get_session_messages(session_id),
    }


@router.delete("/api/chat/sessions/{session_id}", dependencies=_AUTH)
def delete_session(session_id: str) -> Dict[str, Any]:
    if not get_session_store().delete_session(session_id):
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.")
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
    # Origin dan token diperiksa di sini, bukan diserahkan ke browser.
    if not origin_matches_host(websocket) or not token_ok(websocket_token(websocket)):
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
            await _handle_query(websocket, copilot, payload)

        elif kind == "TRIGGER_CANVAS_COMMAND":
            await websocket.send_json({"type": "CANVAS_COMMAND", "payload": payload})


async def _handle_query(
    websocket: WebSocket, copilot: Copilot, payload: Dict[str, Any]
) -> None:
    query = str(payload.get("message") or "").strip()
    if not query:
        return

    store = get_session_store()
    session_id = payload.get("session_id")
    if session_id:
        store.ensure_session(str(session_id))
        session_id = str(session_id)
    else:
        session_id = store.create_session()["id"]

    store.append_message(session_id=session_id, role="user", content=query)
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

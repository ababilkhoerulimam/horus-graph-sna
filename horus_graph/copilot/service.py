"""
Fasad copilot: satu tempat yang mengubah pertanyaan menjadi jawaban.

Jalur utama memakai LLM dengan tool calling. Bila gateway belum dikonfigurasi,
kueri gagal, atau SDK tidak ada, jawaban diambil dari `fallback` deterministik
yang memakai tool yang sama. Tidak ada router kedua: intent, tool, dan angka
selalu berasal dari sumber yang sama.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional

from ..api.state import AppState
from . import fallback, intent as intent_mod, llm, tools
from .prompt import build_persona, centre_label, example_lines

logger = logging.getLogger("horus_graph.copilot")

MAX_HISTORY = 6
MAX_TOOL_TURNS = 3

FOCUS = {
    "Graph Analyst": (
        "Fokus: topologi. Telusuri jalur, betweenness, dan constraint sebelum "
        "menyimpulkan. Sebut angka hanya bila berasal dari tool."
    ),
    "Strategic Intelligence": (
        "Fokus: sintesis. Rangkai temuan struktural menjadi implikasi dan opsi "
        "tindakan. Kutip angka dari tool, jangan menghitung ulang sendiri."
    ),
}


class Copilot:
    """Satu instance per bundle; tidak menyimpan status percakapan."""

    def __init__(self, state: AppState) -> None:
        self.state = state

    # --- publik ------------------------------------------------------------

    def greeting(self) -> str:
        wording = self.state.presentation.wording
        template = wording.get("chip_greeting")
        if template:
            return template.format(
                label=centre_label(self.state),
                centre=centre_label(self.state),
                articles=self.state.presentation.label("articles", "artikel"),
            )
        summary = self.state.network.summary
        return (
            f"Copilot siap pada {self.state.presentation.title}: "
            f"{summary.get('nodes')} simpul, {summary.get('edges')} sisi."
        )

    def dossier(self, entity_id: str) -> Dict[str, Any]:
        """Ringkasan instan saat simpul diklik di kanvas."""
        return tools.execute(self.state, "get_entity_dossier", {"entity_name": entity_id})

    async def answer(
        self, query: str, history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        text = (query or "").strip()
        if not text:
            return _message("Copilot", "Pertanyaan kosong.")

        if not llm.llm_available():
            result = fallback.answer(self.state, text)
            result["llm"] = False
            return result

        try:
            result = await self._run_agent(text, history or [])
            result["llm"] = True
            return result
        except Exception as exc:  # noqa: BLE001 - gateway bisa gagal dengan cara apa pun
            logger.warning("Agen LLM gagal (%s), memakai jawaban deterministik.", exc)
            result = fallback.answer(self.state, text)
            result["llm"] = False
            result["llm_error"] = f"{type(exc).__name__}: {exc}"
            return result

    # --- agen --------------------------------------------------------------

    async def _run_agent(
        self, query: str, history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        intent = intent_mod.classify(query)
        agent = intent_mod.agent_for(intent)

        system_text = "\n\n".join(
            block
            for block in (
                build_persona(self.state),
                FOCUS.get(agent, ""),
                "## Contoh pertanyaan\n" + example_lines(self.state),
            )
            if block
        )

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_text}]
        for item in history[-MAX_HISTORY:]:
            if item.get("role") in ("user", "assistant") and item.get("content"):
                messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": query})

        specs = tools.tool_specs(self.state) if intent_mod.needs_tools(intent) else None
        command: Optional[Dict[str, Any]] = None
        called: List[str] = []

        for turn in range(MAX_TOOL_TURNS):
            active = specs if turn < MAX_TOOL_TURNS - 1 else None
            response = await llm.call_llm(messages, tools=active)
            message = response.choices[0].message

            if not message.tool_calls or active is None:
                final = (message.content or "").strip()
                if final:
                    return _message(agent, final, command, called, intent)
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in message.tool_calls
                    ],
                }
            )

            for call in message.tool_calls:
                name = call.function.name
                called.append(name)
                arguments = _parse_arguments(call.function.arguments)
                result = tools.execute(self.state, name, arguments)
                command = _canvas_from(self.state, name, result, command, query)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        messages.append(
            {
                "role": "user",
                "content": (
                    "Berdasarkan data tool di atas, jawab pertanyaan awal sekarang. "
                    "Sebutkan hanya angka yang muncul pada hasil tool."
                ),
            }
        )
        final_response = await llm.call_llm(messages, tools=None)
        final = (final_response.choices[0].message.content or "").strip()
        if not final:
            result = fallback.answer(self.state, query)
            return {**result, "agent": agent, "intent": intent}
        return _message(agent, final, command, called, intent)


@lru_cache(maxsize=2)
def get_copilot(bundle_path: str) -> Copilot:
    from ..api.state import get_state

    return Copilot(get_state(bundle_path))


def _message(
    agent: str,
    text: str,
    command: Optional[Dict[str, Any]] = None,
    called: Optional[List[str]] = None,
    intent: str = "unknown",
) -> Dict[str, Any]:
    return {
        "agent": agent,
        "text": text,
        "canvas_command": command,
        "tools_called": called or [],
        "intent": intent,
    }


def _parse_arguments(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _canvas_from(
    state: AppState,
    name: str,
    result: Dict[str, Any],
    current: Optional[Dict[str, Any]],
    query: str,
) -> Optional[Dict[str, Any]]:
    """Terjemahkan hasil tool menjadi perintah kanvas; tool terakhir menang."""
    if result.get("status") not in ("ready", None):
        return current

    if name == "direct_canvas_view":
        payload = {key: value for key, value in result.items() if key != "status"}
        return payload or current

    if name == "trace_causal_path" and result.get("path"):
        path = result["path"]
        return {"action": "HIGHLIGHT_PATH", "path": path, "focus_target": path[-1]}

    if name == "get_entity_dossier" and result.get("id"):
        # Membuka profil pusat jaringan tidak boleh menggeser kamera: pertanyaan
        # perbandingan akan kehilangan konteks. Kecuali pengguna meminta profil.
        ego = state.presentation.ego
        if ego is not None and result["id"] == ego.id and "profil" not in query.lower():
            return current
        return {"action": "CANVAS_FOCUS", "node_id": result["id"], "scale": 1.2}

    if name in ("get_broker_ranking", "get_structural_holes_ranking"):
        ranking = result.get("ranking") or []
        if ranking:
            return {"action": "CANVAS_FOCUS", "node_id": ranking[0]["id"], "scale": 1.2}

    if name == "get_sentiment_ranking":
        ranking = result.get("ranking") or []
        if ranking:
            return {"action": "CANVAS_FOCUS", "node_id": ranking[0]["id"], "scale": 1.15}

    if name == "simulate_what_if_scenario" and result.get("removed"):
        return {"action": "CANVAS_FOCUS", "node_id": result["removed"]["id"], "scale": 1.2}

    return current

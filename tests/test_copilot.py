"""
Copilot: tool, jawaban deterministik, WebSocket, dan riwayat sesi.

Semua diuji pada bundle sintetis, tanpa LLM dan tanpa data nyata. Yang dijaga
adalah dua hal: setiap tool membaca `AppState` yang sama dengan endpoint HTTP,
dan tidak ada nama domain yang bocor ke dalam kode.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from horus_graph.api.app import create_app
from horus_graph.api.state import AppState
from horus_graph.contract import schema
from horus_graph.contract.models import Presentation as PresentationMeta
from horus_graph.core.anomaly import detect_anomalies
from horus_graph.core.bipartite import build_bipartite
from horus_graph.core.build import build_network
from horus_graph.core.temporal import build_temporal
from horus_graph.copilot import fallback, intent as intent_mod, tools
from horus_graph.io import write_bundle
from horus_graph.presentation import resolve_presentation

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

# Nama domain yang tidak boleh muncul di paket. Daftar ini sengaja pendek:
# yang dijaga adalah bukti bahwa repo bisa di-fork tanpa menyunting kode.
DOMAIN_WORDS = (
    "dewa united",
    "liga 1",
    "sepak bola",
    "riekerink",
    "persib",
    "persija",
    "antaranews",
    "karhutla",
)


def _pad(frame: pd.DataFrame, target: pa.Schema) -> pd.DataFrame:
    padded = frame.copy()
    for field in target:
        if field.name not in padded.columns:
            padded[field.name] = None
    return padded


def _write_bundle(root: Path, bundle_factory) -> Path:
    """Rantai Alpha-Bravo-Charlie-Delta-Echo di atas 90 artikel, dua epos."""
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 10) for e in ("Alpha", "Bravo")]
    rows += [(f"art{i:03d}", e, 1) for i in range(10, 20) for e in ("Bravo", "Charlie")]
    rows += [(f"art{i:03d}", e, 1) for i in range(20, 30) for e in ("Charlie", "Delta")]
    rows += [(f"art{i:03d}", e, 1) for i in range(30, 40) for e in ("Delta", "Echo")]
    dates = ["2021-06-01"] * 45 + ["2023-06-01"] * 45

    bundle = bundle_factory(
        ["Alpha", "Bravo", "Charlie", "Delta", "Echo"],
        rows,
        articles=90,
        ego="Alpha",
        dates=dates,
        epochs=[("e1", 2021, 2022), ("e2", 2023, 2024)],
        topics=["T1"],
        article_topics=[(f"art{i:03d}", "T1") for i in range(0, 20)],
    )

    write_bundle(
        root,
        frames={
            "entities": _pad(bundle.entities, schema.ENTITIES),
            "articles": _pad(bundle.articles, schema.ARTICLES),
            "mentions": _pad(bundle.mentions, schema.MENTIONS),
            "topics": _pad(bundle.topics, schema.TOPICS),
            "article_topics": _pad(bundle.article_topics, schema.ARTICLE_TOPICS),
        },
        domain=bundle.domain,
        dataset_id="synthetic",
        date_range=(date(2021, 1, 1), date(2024, 12, 31)),
        generator="tests/copilot",
    )
    return root


@pytest.fixture()
def client(tmp_path, bundle_factory) -> TestClient:
    root = _write_bundle(tmp_path / "bundle", bundle_factory)
    return TestClient(create_app(root))


@pytest.fixture()
def state(client) -> AppState:
    from horus_graph.api.state import get_state

    return get_state(client.app.state.bundle_path)


# --- kontrak tool ----------------------------------------------------------


def test_health_menyatakan_copilot_dan_llm(client):
    payload = client.get("/api/health").json()

    assert payload["capabilities"]["copilot"] is True
    # Tanpa variabel lingkungan, jawaban bebas tidak tersedia tetapi drawer tetap ada.
    assert payload["capabilities"]["llm"] is False


def test_ada_dua_puluh_tool(state):
    specs = tools.tool_specs(state)
    names = [item["function"]["name"] for item in specs]

    assert len(names) == 20
    assert len(set(names)) == 20
    assert set(names) == set(tools.tool_names())


def test_deskripsi_tool_memakai_entitas_dari_bundle(state):
    specs = {item["function"]["name"]: item["function"] for item in tools.tool_specs(state)}
    dossier = specs["get_entity_dossier"]["parameters"]["properties"]["entity_name"]["description"]

    assert "'Alpha'" in dossier
    assert "dewa" not in dossier.lower()


def test_setiap_tool_punya_parameter_bertipe(state):
    for item in tools.tool_specs(state):
        function = item["function"]
        assert function["description"]
        parameters = function["parameters"]
        assert parameters["type"] == "object"
        for name, spec in parameters["properties"].items():
            assert "type" in spec, f"{function['name']}.{name} tanpa tipe"


def test_semua_tool_dapat_dijalankan(state):
    calls = {
        "get_network_overview": {},
        "get_entity_dossier": {"entity_name": "Bravo"},
        "trace_causal_path": {"origin": "Alpha", "target": "Charlie"},
        "filter_subgraph": {"topic": "ALL", "start_year": 2021, "end_year": 2024},
        "get_broker_ranking": {"limit": 3},
        "get_hawkes_transmissions": {},
        "explain_wire_transmission": {"source_media": "Alpha", "target_media": "Bravo"},
        "search_news_narratives": {"query": "art"},
        "get_sentiment_ranking": {"sentiment_type": "negative"},
        "simulate_what_if_scenario": {"target_node": "Delta"},
        "direct_canvas_view": {"action": "FOCUS_NODE", "target_nodes": ["Bravo"]},
        "generate_executive_briefing": {},
        "get_structural_holes_ranking": {"mode": "high_autonomy"},
        "get_entity_temporal_trajectory": {"entity_name": "Charlie"},
        "get_topic_actor_network": {"min_npmi": 0.0},
        "compare_network_periods": {"baseline_period": "e1", "target_period": "e2"},
        "get_edge_evidence": {"source": "Alpha", "target": "Bravo"},
        "list_entities": {"limit": 5},
        "get_anomaly_report": {},
        "get_glossary": {"term": "betweenness"},
    }

    assert set(calls) == set(tools.tool_names())
    for name, arguments in calls.items():
        result = tools.execute(state, name, arguments)
        assert isinstance(result, dict), name
        assert "status" in result, name
        assert result["status"] not in ("error", "unknown_tool"), (name, result)


def test_tool_tidak_dikenal_dikembalikan_sebagai_status(state):
    result = tools.execute(state, "tidak_ada", {})

    assert result["status"] == "unknown_tool"
    assert "get_network_overview" in result["available_tools"]


def test_lapisan_yang_belum_ada_dilaporkan_jujur(state):
    result = tools.execute(state, "get_hawkes_transmissions", {})

    assert result["status"] == "awaiting_input"
    assert result["layer"] == "transmission"


def test_filter_subgraph_memakai_peta_topik_ke_entitas(state):
    """`membership` adalah topic_id -> entitas, bukan sebaliknya."""
    membership = state.bipartite.membership
    topic = next(iter(membership))
    expected = {str(value) for value in membership[topic]}

    result = tools.execute(
        state, "filter_subgraph", {"topic": topic, "start_year": 2021, "end_year": 2024}
    )

    assert result["status"] == "ready"
    assert set(result["node_ids"]) <= expected
    assert result["count"] == len(result["node_ids"])


def test_topic_tidak_dikenal_mengembalikan_pilihan(state):
    result = tools.execute(state, "filter_subgraph", {"topic": "TIDAK_ADA"})

    assert result["status"] == "empty"
    assert result["available_topics"]


# --- jawaban deterministik -------------------------------------------------


def test_fallback_overview_memakai_angka_state(state):
    result = fallback.answer(state, "Ringkas topologi jaringan")
    summary = state.network.summary

    assert result["intent"] == "overview"
    assert result["fallback"] is True
    assert str(summary["nodes"]) in result["text"]
    assert str(summary["edges"]) in result["text"]


def test_fallback_broker_menyebut_entitas_nyata(state):
    result = fallback.answer(state, "Siapa aktor broker terpenting?")

    assert result["intent"] == "broker"
    assert "Broker teratas" in result["text"]
    assert result["canvas_command"]["action"] == "CANVAS_FOCUS"


def test_fallback_jalur_mengirim_perintah_kanvas(state):
    result = fallback.answer(state, "Bagaimana jalur dari Alpha ke Charlie?")

    assert result["intent"] == "path"
    assert "Alpha" in result["text"] and "Charlie" in result["text"]
    assert result["canvas_command"]["action"] == "HIGHLIGHT_PATH"


def test_fallback_whatif_menolak_menghapus_pusat(state):
    result = fallback.answer(state, "Bagaimana jika Alpha absen?")

    assert result["intent"] == "whatif"
    assert "pusat" in result["text"].lower()


def test_fallback_sentimen_jujur_soal_lapisan_kosong(state):
    result = fallback.answer(state, "Bagaimana sentimen seputar Bravo?")

    assert result["intent"] == "sentiment"
    assert "belum tersedia" in result["text"].lower()


def test_fallback_glosarium_menjawab_istilah(state):
    result = fallback.answer(state, "apa itu betweenness")

    assert result["intent"] == "glossary"
    assert result["text"].startswith("betweenness:")


def test_alias_entitas_dikenali(state):
    found = intent_mod.find_entities(state, "bagaimana jalur dari Alpha ke Bravo?")

    assert found[:2] == ["Alpha", "Bravo"]


def test_kalimat_fallback_dapat_ditimpa_bundle(bundle_factory):
    bundle = bundle_factory(
        ["Alpha", "Bravo"],
        [("art000", "Alpha", 1), ("art000", "Bravo", 1)],
        articles=2,
    )
    bundle.manifest.presentation = PresentationMeta(
        wording={"fallback_overview": "KALIMAT KHUSUS {nodes} simpul."}
    )
    state = _state_of(bundle)
    result = fallback.answer(state, "ringkas topologi")

    assert result["text"] == f"KALIMAT KHUSUS {state.network.summary['nodes']} simpul."


# --- websocket dan sesi ----------------------------------------------------


def test_websocket_mengirim_dossier_dan_jawaban(client):
    with client.websocket_connect("/ws/copilot") as socket:
        connected = socket.receive_json()
        assert connected["type"] == "SYSTEM_CONNECTED"
        assert connected["payload"]["llm"] is False

        socket.send_json({"type": "PING"})
        assert socket.receive_json()["type"] == "PONG"

        socket.send_json({"type": "NODE_SELECTED", "payload": {"node_id": "Bravo"}})
        dossier = socket.receive_json()
        assert dossier["type"] == "NODE_DOSSIER_READY"
        assert dossier["payload"]["label"] == "Bravo"

        socket.send_json(
            {"type": "USER_CHAT_QUERY", "payload": {"message": "Siapa broker teratas?"}}
        )
        answer = socket.receive_json()
        assert answer["type"] == "AGENT_MESSAGE"
        assert answer["payload"]["text"]
        assert answer["payload"]["session_id"]


def test_websocket_mengadopsi_id_sesi_dari_klien(client):
    session = client.post("/api/chat/sessions", json={"title": "uji"}).json()

    with client.websocket_connect("/ws/copilot") as socket:
        socket.receive_json()
        socket.send_json(
            {
                "type": "USER_CHAT_QUERY",
                "payload": {"message": "ringkas topologi", "session_id": session["id"]},
            }
        )
        answer = socket.receive_json()

    assert answer["payload"]["session_id"] == session["id"]
    messages = client.get(f"/api/chat/sessions/{session['id']}/messages").json()["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant"]


def test_sesi_chat_dapat_dibuat_dibaca_dan_dihapus(client):
    created = client.post("/api/chat/sessions", json={"title": "mulai"}).json()
    listed = client.get("/api/chat/sessions").json()["sessions"]

    assert any(item["id"] == created["id"] for item in listed)

    deleted = client.delete(f"/api/chat/sessions/{created['id']}")
    assert deleted.status_code == 200
    assert client.delete(f"/api/chat/sessions/{created['id']}").status_code == 404


def test_node_tidak_dikenal_dilaporkan_sebagai_error(client):
    with client.websocket_connect("/ws/copilot") as socket:
        socket.receive_json()
        socket.send_json({"type": "NODE_SELECTED", "payload": {"node_id": "ZZZ"}})
        error = socket.receive_json()

    assert error["type"] == "AGENT_ERROR"
    assert "ZZZ" in error["payload"]["error"]


# --- tanpa pusat -----------------------------------------------------------


def test_copilot_berjalan_tanpa_pusat(bundle_factory, tmp_path):
    bundle = bundle_factory(
        ["Alpha", "Bravo"],
        [("art000", "Alpha", 1), ("art000", "Bravo", 1)],
        articles=2,
        ego="",
        entity_types=["Entity", "Entity"],
        dates=["2021-06-01", "2021-06-01"],
    )
    root = tmp_path / "noego"
    write_bundle(
        root,
        frames={
            "entities": _pad(bundle.entities, schema.ENTITIES),
            "articles": _pad(bundle.articles, schema.ARTICLES),
            "mentions": _pad(bundle.mentions, schema.MENTIONS),
            "topics": _pad(bundle.topics, schema.TOPICS),
            "article_topics": _pad(bundle.article_topics, schema.ARTICLE_TOPICS),
        },
        domain=bundle.domain,
        dataset_id="noego",
        date_range=(date(2021, 1, 1), date(2021, 12, 31)),
        generator="tests/copilot",
    )
    client = TestClient(create_app(root))

    assert client.get("/api/health").json()["capabilities"]["copilot"] is True
    with client.websocket_connect("/ws/copilot") as socket:
        connected = socket.receive_json()
        assert connected["type"] == "SYSTEM_CONNECTED"
        assert "tanpa pusat" not in connected["payload"]["title"]

    overview = client.get("/api/copilot/tools").json()
    assert len(overview["tools"]) == 20


# --- pagar domain ----------------------------------------------------------


def test_paket_tidak_memuat_nama_domain():
    """Fork repo + bundle baru harus cukup, tanpa menyunting satu baris pun."""
    offenders = []
    for path in (REPO_ROOT / "horus_graph").rglob("*"):
        if path.suffix not in (".py", ".js", ".html", ".css"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for word in DOMAIN_WORDS:
            if word in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {word}")

    assert offenders == []


def _state_of(bundle) -> AppState:
    return AppState(
        root=REPO_ROOT,
        bundle=bundle,
        presentation=resolve_presentation(bundle),
        network=build_network(bundle),
        temporal=build_temporal(bundle),
        bipartite=build_bipartite(bundle),
        anomaly=detect_anomalies(bundle),
        build_seconds=0.0,
    )

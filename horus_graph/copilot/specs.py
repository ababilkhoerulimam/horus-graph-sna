"""
Deskripsi tool copilot, dirakit dari data.

Tidak ada nama domain di file ini. Contoh entitas diambil dari simpul berderajat
tertinggi, tipe dari `presentation.entity_types`, dan daftar epos serta topik
dari state aktif. Bundle baru otomatis menghasilkan deskripsi yang berbeda
tanpa menyunting kode.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..api.state import AppState
from .prompt import top_entities

CANVAS_ACTIONS = (
    "FOCUS_NODE",
    "ISOLATE_CLUSTER",
    "COMPARE_NODES",
    "TRIGGER_TRACE",
    "RESET_VIEW",
)


def _labels(state: AppState, limit: int = 4) -> str:
    """Contoh label entitas untuk deskripsi tool."""
    items = [item["label"] for item in top_entities(state, limit=limit)]
    if not items:
        return "nama entitas"
    return ", ".join(f"'{label}'" for label in items)


def _types(state: AppState) -> str:
    values = [style.id for style in state.presentation.entity_types.values()]
    return ", ".join(values) if values else "tipe entitas"


def epoch_ids(state: AppState) -> List[str]:
    return [item.window.id for item in state.temporal.slices if item.window.id != "all_time"]


def topic_ids(state: AppState) -> List[str]:
    frame = state.bipartite.topics
    if frame.empty:
        return []
    return [str(value) for value in frame["topic_id"].tolist()]


def tool_specs(state: AppState) -> List[Dict[str, Any]]:
    """
    Skema function-calling untuk semua tool.

    Deskripsi memuat contoh entitas nyata supaya model memanggil dengan nama
    yang benar, tanpa satu pun nama domain ditulis di file ini.
    """
    examples = _labels(state)
    types = _types(state)
    epochs = epoch_ids(state) or ["epoch_1"]
    topics = topic_ids(state) or ["ALL"]

    def spec(name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or [],
                },
            },
        }

    entity_prop = {"type": "string", "description": f"Nama entitas, mis. {examples}"}

    return [
        spec(
            "get_network_overview",
            "Statistik makro jaringan aktif: jumlah simpul, sisi, kepadatan, modularitas, dan status setiap lapisan opsional.",
            {},
        ),
        spec(
            "get_entity_dossier",
            "Profil lengkap satu entitas: sentralitas, peran lubang struktural, tetangga terkuat, lintasan antar-epos, dan sentimen bila tersedia.",
            {"entity_name": entity_prop},
            ["entity_name"],
        ),
        spec(
            "trace_causal_path",
            "Rute terkuat antara dua entitas beserta jalur alternatif dan broker kritisnya.",
            {"origin": entity_prop, "target": entity_prop},
            ["origin", "target"],
        ),
        spec(
            "filter_subgraph",
            "Daftar simpul yang aktif pada rentang tahun tertentu, opsional disaring satu topik. Dipakai untuk menyiapkan sorotan kanvas.",
            {
                "topic": {"type": "string", "description": f"Id topik, atau ALL. Pilihan: {', '.join(topics)}"},
                "start_year": {"type": "integer"},
                "end_year": {"type": "integer"},
            },
        ),
        spec(
            "get_broker_ranking",
            "Peringkat simpul dengan betweenness tertinggi, yaitu jembatan antar kelompok.",
            {
                "entity_type": {"type": "string", "description": f"Penyaring tipe. Pilihan: {types}"},
                "limit": {"type": "integer", "default": 5},
            },
        ),
        spec(
            "get_hawkes_transmissions",
            "Parameter transmisi antar sumber berita (alpha, selang kepercayaan, lead time). Mengembalikan awaiting_input bila lapisan ini belum ada di bundle.",
            {"limit": {"type": "integer", "default": 50}},
        ),
        spec(
            "explain_wire_transmission",
            "Rincian satu tepi transmisi dari satu sumber ke satu penerima.",
            {"source_media": entity_prop, "target_media": entity_prop},
            ["source_media", "target_media"],
        ),
        spec(
            "search_news_narratives",
            "Cari artikel korpus berdasarkan kata kunci judul, opsional dibatasi artikel yang menyebut satu entitas. Isi artikel tidak tersedia, hanya judul.",
            {
                "query": {"type": "string"},
                "entity_name": entity_prop,
                "limit": {"type": "integer", "default": 10},
            },
            ["query"],
        ),
        spec(
            "get_sentiment_ranking",
            "Peringkat entitas menurut persentase sentimen negatif atau positif. awaiting_input bila skor sentimen belum ada.",
            {
                "sentiment_type": {"type": "string", "enum": ["negative", "positive"]},
                "entity_type": {"type": "string", "description": f"Pilihan: {types}"},
                "limit": {"type": "integer", "default": 5},
            },
        ),
        spec(
            "simulate_what_if_scenario",
            "Simulasi kontrafaktual: hapus satu simpul dan ukur pergeseran kepadatan, broker pengganti, dan simpul yang terisolasi.",
            {"target_node": entity_prop},
            ["target_node"],
        ),
        spec(
            "direct_canvas_view",
            "Kirim perintah visual ke kanvas. Gunakan hanya bila pengguna meminta manipulasi tampilan.",
            {
                "action": {"type": "string", "enum": list(CANVAS_ACTIONS)},
                "target_nodes": {"type": "array", "items": {"type": "string"}},
                "cluster_name": {"type": "string"},
            },
            ["action"],
        ),
        spec(
            "generate_executive_briefing",
            "Kompilasi briefing eksekutif: makro topologi, broker kritis, radar ancaman, anomali bulanan, dan status lapisan.",
            {},
        ),
        spec(
            "get_structural_holes_ranking",
            "Peringkat Burt: constraint terendah (otonomi tinggi) atau tertinggi (terkunci dalam clique redundan).",
            {
                "mode": {"type": "string", "enum": ["high_autonomy", "high_constraint"]},
                "limit": {"type": "integer", "default": 10},
            },
        ),
        spec(
            "get_entity_temporal_trajectory",
            "Lintasan satu entitas per epos: derajat, betweenness, constraint, dan jumlah artikel, plus perbandingan dua epos terakhir.",
            {"entity_name": entity_prop},
            ["entity_name"],
        ),
        spec(
            "get_topic_actor_network",
            "Jaringan bipartite topik-aktor dengan bobot NPMI dan ambang minimum.",
            {
                "topic_filter": {"type": "string", "description": f"Id topik atau ALL. Pilihan: {', '.join(topics)}"},
                "min_npmi": {"type": "number", "default": 0.0},
            },
        ),
        spec(
            "compare_network_periods",
            "Delta derajat, betweenness, dan constraint antara dua epos, termasuk simpul yang masuk dan keluar.",
            {
                "baseline_period": {"type": "string", "description": f"Pilihan: {', '.join(epochs)}"},
                "target_period": {"type": "string", "description": f"Pilihan: {', '.join(epochs)}"},
            },
        ),
        spec(
            "get_edge_evidence",
            "Bobot, NPMI, dan artikel bersama yang membuktikan satu relasi.",
            {
                "source": entity_prop,
                "target": entity_prop,
                "limit": {"type": "integer", "default": 5},
            },
            ["source", "target"],
        ),
        spec(
            "list_entities",
            "Telusuri katalog entitas, diurutkan menurut derajat, betweenness, constraint, atau jumlah artikel.",
            {
                "entity_type": {"type": "string", "description": f"Pilihan: {types}"},
                "order": {
                    "type": "string",
                    "enum": ["degree", "betweenness", "constraint", "articles"],
                },
                "limit": {"type": "integer", "default": 20},
            },
        ),
        spec(
            "get_anomaly_report",
            "Lonjakan jumlah artikel per bulan beserta z-score dan tingkat keparahannya.",
            {},
        ),
        spec(
            "get_glossary",
            "Definisi istilah metrik jaringan yang dipakai sistem ini.",
            {"term": {"type": "string"}},
        ),
    ]

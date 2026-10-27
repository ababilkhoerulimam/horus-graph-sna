"""
Router intent.

Kata kunci di sini adalah kosakata analitis (broker, sentimen, jalur, memo),
bukan kosakata domain. Karena itu daftar yang sama berlaku untuk bundle apa pun.
"""

from __future__ import annotations

import re
from typing import Dict, List

from ..api.state import AppState

INTENTS = (
    "greeting",
    "casual",
    "overview",
    "dossier",
    "path",
    "broker",
    "holes",
    "sentiment",
    "whatif",
    "briefing",
    "topic",
    "compare",
    "anomaly",
    "corpus",
    "canvas",
    "glossary",
    "unknown",
)

# Urutan penting: pola yang lebih spesifik diperiksa lebih dulu.
INTENT_PATTERNS: List[tuple[str, tuple[str, ...]]] = [
    ("glossary", ("apa itu", "apa yang dimaksud", "definisi", "arti istilah", "maksud istilah", "glosarium", "glossary")),
    ("whatif", ("what if", "what-if", "bagaimana jika", "bagaimana kalau", "jika", "kalau", "absen", "keluar dari", "dihapus", "hilang", "tanpa ", "simulasi", "kontrafaktual", "dampak kehilangan")),
    ("briefing", ("memo", "briefing", "laporan", "executive", "ringkasan eksekutif")),
    ("anomaly", ("anomali", "lonjakan", "spike", "meledak", "puncak bulan", "bulan mana")),
    ("path", ("jalur", "path", "rute", "lintasan dari", "menuju", "sampai ke", "trace", "rantai")),
    ("sentiment", ("sentimen", "sentiment", "negatif", "positif", "kritik", "kritis", "opini", "framing")),
    ("broker", ("broker", "jembatan", "betweenness", "perantara", "penghubung", "mediator")),
    ("holes", ("lubang struktural", "structural hole", "constraint", "burt", "otonomi", "effective size")),
    ("compare", ("bandingkan", "perbandingan", "compare", "delta", "antar epos", "antar-epos", "perubahan antar", "evolusi")),
    ("topic", ("topik", "topic", "tema", "wacana", "bipartite", "npmi")),
    ("corpus", ("artikel", "berita", "judul", "cari", "sebut", "kutipan", "teks")),
    ("canvas", ("sorot", "fokus", "tampilkan", "isolasi", "reset", "kembalikan tampilan", "zoom")),
    ("overview", ("ringkas", "overview", "gambaran", "statistik", "berapa simpul", "berapa sisi", "kepadatan", "modularitas", "topologi")),
    ("dossier", ("profil", "dossier", "siapa", "peran", "tentang", "jelaskan", "analisis")),
]

GREETINGS = (
    "halo",
    "hai",
    "hi",
    "hello",
    "selamat pagi",
    "selamat siang",
    "selamat malam",
    "assalamualaikum",
    "pagi",
    "siang",
    "malam",
)

CASUAL_MAX_WORDS = 4

GRAPH_INTENTS = frozenset(
    {"overview", "dossier", "path", "broker", "holes", "sentiment", "whatif", "briefing", "topic", "compare", "anomaly", "corpus", "glossary"}
)

AGENT_FOR: Dict[str, str] = {
    "overview": "Graph Analyst",
    "dossier": "Graph Analyst",
    "path": "Graph Analyst",
    "broker": "Graph Analyst",
    "holes": "Graph Analyst",
    "topic": "Graph Analyst",
    "compare": "Graph Analyst",
    "anomaly": "Graph Analyst",
    "glossary": "Graph Analyst",
    "sentiment": "Strategic Intelligence",
    "whatif": "Strategic Intelligence",
    "briefing": "Strategic Intelligence",
    "corpus": "Strategic Intelligence",
    "canvas": "Canvas Director",
    "greeting": "Copilot",
    "casual": "Copilot",
    "unknown": "Graph Analyst",
}


def classify(query: str) -> str:
    """Intent pertama yang cocok; `unknown` bila tidak ada pola yang kena."""
    text = (query or "").strip().lower()
    if not text:
        return "unknown"

    if text in GREETINGS or any(text.startswith(greeting + " ") for greeting in GREETINGS):
        return "greeting"

    for intent, patterns in INTENT_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return intent

    if len(text.split()) <= CASUAL_MAX_WORDS:
        return "casual"
    return "unknown"


def agent_for(intent: str) -> str:
    return AGENT_FOR.get(intent, "Graph Analyst")


def needs_tools(intent: str) -> bool:
    return intent in GRAPH_INTENTS or intent == "canvas"


def find_entities(state: AppState, query: str, limit: int = 4) -> List[str]:
    """
    Entitas yang namanya muncul di dalam pertanyaan.

    Label dan alias dipakai sama rata, dicocokkan pada batas kata, lalu
    diurutkan dari nama terpanjang supaya "Klub A" tidak menutupi "Klub A U-21".
    """
    text = (query or "").lower()
    if not text:
        return []

    best: Dict[str, int] = {}
    for name, entity_id in _alias_index(state):
        if _contains_word(text, name):
            best[entity_id] = max(best.get(entity_id, 0), len(name))

    ordered = sorted(best.items(), key=lambda item: (-item[1], item[0]))
    return [entity_id for entity_id, _ in ordered[:limit]]


_INDEX_CACHE: Dict[int, tuple["AppState", tuple[tuple[str, str], ...]]] = {}


def _alias_index(state: AppState) -> tuple[tuple[str, str], ...]:
    """
    Pasangan (nama huruf kecil, id entitas), di-cache per objek state.

    State disimpan bersama cache supaya `id()` tidak dipakai ulang oleh objek
    lain setelah garbage collection.
    """
    cached = _INDEX_CACHE.get(id(state))
    if cached is not None and cached[0] is state:
        return cached[1]

    pairs: set[tuple[str, str]] = set()
    entities = state.bundle.entities
    if not entities.empty:
        for row in entities.itertuples(index=False):
            entity_id = str(row.entity_id)
            for value in (getattr(row, "label", None), *_alias_values(row)):
                if not isinstance(value, str):
                    continue
                name = value.strip().lower()
                if len(name) >= 3:
                    pairs.add((name, entity_id))

    ordered = tuple(sorted(pairs, key=lambda item: (-len(item[0]), item[0])))
    if len(_INDEX_CACHE) > 8:
        # State lama dipegang cache ini; jangan sampai menahan bundle yang sudah
        # tidak dipakai proses.
        _INDEX_CACHE.clear()
    _INDEX_CACHE[id(state)] = (state, ordered)
    return ordered


def _alias_values(row) -> List[str]:
    aliases = getattr(row, "aliases", None)
    if aliases is None:
        return []
    if isinstance(aliases, str):
        return [aliases]
    try:
        return [str(value) for value in aliases]
    except TypeError:
        return []


def _contains_word(haystack: str, needle: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def describe(intent: str) -> str:
    return {
        "greeting": "sapaan",
        "casual": "obrolan singkat",
        "overview": "ringkasan topologi",
        "dossier": "profil entitas",
        "path": "penelusuran jalur",
        "broker": "peringkat broker",
        "holes": "lubang struktural",
        "sentiment": "analisis sentimen",
        "whatif": "simulasi kontrafaktual",
        "briefing": "memo eksekutif",
        "topic": "jaringan topik",
        "compare": "perbandingan epos",
        "anomaly": "anomali bulanan",
        "corpus": "penelusuran korpus",
        "canvas": "kendali kanvas",
        "glossary": "penjelasan istilah",
        "unknown": "pertanyaan umum",
    }.get(intent, intent)

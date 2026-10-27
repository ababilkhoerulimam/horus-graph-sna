"""
Lapisan opsional: transmisi media dan sentimen entitas.

Keduanya boleh tidak ada. Engine tidak pernah mengisi nilai pengganti: tanpa
lapisan, `transmission_layer` dan `sentiment_layer` mengembalikan `None`, dan
seluruh turunannya (alpha, lead time, stance, peringkat sentimen) menjadi
`None` dengan status `awaiting_input`. Nol akan terbaca sebagai "terukur nol",
padahal artinya "belum ada data".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import networkx as nx

from .._coerce import is_missing
from ..io.bundle import DataBundle


@dataclass(frozen=True)
class TransmissionLayer:
    """Graf terarah media -> media beserta parameter Hawkes per tepi."""

    graph: nx.DiGraph
    method: Optional[str]
    n_edges: int

    def severed_routes(self, entity_id: str) -> int:
        """Jumlah rute transmisi yang melewati simpul ini (masuk + keluar)."""
        if entity_id not in self.graph:
            return 0
        return int(self.graph.in_degree(entity_id) + self.graph.out_degree(entity_id))


@dataclass(frozen=True)
class SentimentLayer:
    """Skor sentimen per entitas dalam persen (pos + neu + neg ≈ 100)."""

    scores: Mapping[str, Mapping[str, Any]]
    method: Optional[str]
    n_entities: int


def transmission_layer(bundle: DataBundle) -> Optional[TransmissionLayer]:
    frame = bundle.transmission
    if frame is None or frame.empty:
        return None

    graph = nx.DiGraph()
    for row in frame.itertuples(index=False):
        graph.add_edge(
            str(row.src),
            str(row.dst),
            alpha=float(row.alpha),
            alpha_ci_low=float(row.alpha_ci_low),
            alpha_ci_high=float(row.alpha_ci_high),
            lead_time_min=float(row.lead_time_min),
            method=str(row.method),
            n_events=None if _is_missing(row.n_events) else int(row.n_events),
            window_start=None if _is_missing(row.window_start) else str(row.window_start),
            window_end=None if _is_missing(row.window_end) else str(row.window_end),
        )

    methods = sorted({str(value) for value in frame["method"].dropna().unique()})
    return TransmissionLayer(
        graph=graph,
        method=", ".join(methods) if methods else None,
        n_edges=len(frame),
    )


def sentiment_layer(bundle: DataBundle) -> Optional[SentimentLayer]:
    frame = bundle.sentiment
    if frame is None or frame.empty:
        return None

    scores: Dict[str, Dict[str, Any]] = {}
    for row in frame.itertuples(index=False):
        scores[str(row.entity_id)] = {
            "pos": float(row.pos),
            "neu": float(row.neu),
            "neg": float(row.neg),
            "method": str(row.method),
            "confidence": None if _is_missing(row.confidence) else float(row.confidence),
            "window_start": None if _is_missing(row.window_start) else str(row.window_start),
            "window_end": None if _is_missing(row.window_end) else str(row.window_end),
        }

    methods = sorted({str(value) for value in frame["method"].dropna().unique()})
    return SentimentLayer(
        scores=scores,
        method=", ".join(methods) if methods else None,
        n_entities=len(scores),
    )


def _is_missing(value: Any) -> bool:
    return is_missing(value)


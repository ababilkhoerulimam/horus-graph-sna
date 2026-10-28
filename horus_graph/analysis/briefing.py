"""
Briefing eksekutif: kumpulan fakta yang sudah dihitung, tanpa prosa.

Engine sengaja tidak menyusun kalimat. Kalimat butuh bahasa, gaya, dan konteks
domain yang bukan urusan engine; yang engine jamin adalah angka dan statusnya.
Lapisan aplikasi (horus-agent) yang merangkai ini menjadi narasi.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.anomaly import AnomalyReport
from ..core.bipartite import TopicActorBundle
from ..core.build import NetworkBundle
from ..core.temporal import TemporalBundle
from .ranking import sentiment_ranking, top_brokers


def executive_briefing(
    network: NetworkBundle,
    temporal: Optional[TemporalBundle] = None,
    anomaly: Optional[AnomalyReport] = None,
    bipartite: Optional[TopicActorBundle] = None,
) -> Dict[str, Any]:
    """Ringkasan makro + anomali + broker kritis + status lapisan opsional."""
    summary = network.summary
    brokers = top_brokers(network, limit=1)

    return {
        "dataset": {
            "domain_id": network.domain.domain_id,
            "label": network.domain.label,
            "ego_id": network.domain.ego_id,
        },
        "macro": {
            "nodes": summary["nodes"],
            "edges": summary["edges"],
            "density": summary["density"],
            "transitivity": summary["transitivity"],
            "components": summary["components"],
            "modularity": summary["communities"]["modularity"],
            "communities": summary["communities"]["count"],
            "community_sizes": list(summary["communities"]["sizes"]),
            "articles": network.corpus_articles,
        },
        "critical_broker": brokers[0] if brokers else None,
        "largest_community": _largest_community(network),
        "threat_radar": sentiment_ranking(network, kind="negative", limit=3),
        "epochs": _epochs(temporal),
        "anomaly": _anomaly(anomaly),
        "topics": _topics(bipartite),
        "layers": {
            "transmission": network.layers.get("transmission", "awaiting_input"),
            "sentiment": network.layers.get("sentiment", "awaiting_input"),
        },
    }


def _largest_community(network: NetworkBundle) -> Optional[Dict[str, Any]]:
    frame = network.node_metrics
    if frame.empty:
        return None
    sizes = frame["louvain_community"].value_counts()
    community = int(sizes.index[0])
    return {"community": community, "size": int(sizes.iloc[0])}


def _epochs(temporal: Optional[TemporalBundle]) -> List[Dict[str, Any]]:
    if temporal is None:
        return []
    return [
        {
            "id": slice_.window.id,
            "label": slice_.window.label,
            "start_year": slice_.window.start_year,
            "end_year": slice_.window.end_year,
            "nodes": slice_.graph.number_of_nodes(),
            "edges": slice_.graph.number_of_edges(),
            "density": slice_.density,
            "articles": slice_.articles,
            "isolated": len(slice_.isolated),
            "top_broker": slice_.top_broker,
        }
        for slice_ in temporal.slices
    ]


def _anomaly(anomaly: Optional[AnomalyReport]) -> Optional[Dict[str, Any]]:
    if anomaly is None:
        return None
    return {
        "months": anomaly.months,
        "partial_periods": list(anomaly.partial_periods),
        "spikes": [dict(spike) for spike in anomaly.spikes],
    }


def _topics(bipartite: Optional[TopicActorBundle]) -> Optional[Dict[str, Any]]:
    if bipartite is None:
        return None
    return bipartite.summary()

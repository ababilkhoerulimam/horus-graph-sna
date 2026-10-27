"""
Dossier entitas: satu profil yang bisa diaudit baris per baris.

Semua angka berasal dari `NetworkBundle` atau `TemporalBundle` yang sudah
dihitung; tidak ada nilai yang diisi ulang dengan default "masuk akal". Kolom
yang tidak tersedia dikembalikan `None` dengan status `awaiting_input`, supaya
pembaca tidak salah membaca absen data sebagai nilai nol.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from ..core.build import NetworkBundle
from ..core.stance import stance_of
from ..core.temporal import TemporalBundle
from .resolve import resolve_entity

SENTIMENT_FIELDS = ("pos", "neu", "neg", "confidence", "method")


def entity_dossier(
    network: NetworkBundle,
    query: str,
    temporal: Optional[TemporalBundle] = None,
    neighbor_limit: int = 8,
) -> Dict[str, Any]:
    """Profil lengkap satu entitas; `KeyError` bila nama tidak bisa diresolusi."""
    entity_id = resolve_entity(network, query)
    if entity_id is None:
        raise KeyError(f"Entitas '{query}' tidak ditemukan di katalog")

    row = network.node_metrics.loc[entity_id]
    graph = network.graph
    scores = network.sentiment.scores if network.sentiment else None

    return {
        "id": entity_id,
        "label": network.label_of(entity_id),
        "entity_type": network.type_of(entity_id),
        "community": int(row["louvain_community"]),
        # `None` bila simpul sendirian di komunitasnya: tidak ada rekan untuk
        # diukur, dan itu bukan berarti keanggotaannya sempurna.
        "community_stability": _float(row.get("community_stability")),
        "degree": int(row["degree"]),
        "pagerank": _float(row["pagerank"]),
        "betweenness": _float(row["betweenness"]),
        "closeness": _float(row["closeness"]),
        "burt_constraint": _float(row["burt_constraint"]),
        "effective_size": _float(row["effective_size"]),
        "structural_hole_role": row["structural_hole_role"],
        "articles": int(row["articles"]),
        "neighbors": _neighbors(network, entity_id, neighbor_limit),
        "trajectory": _trajectory(temporal, entity_id),
        "exposure": _exposure(temporal, entity_id),
        "sentiment": _sentiment(scores, entity_id),
        "in_graph": graph.has_node(entity_id),
    }


def _neighbors(network: NetworkBundle, entity_id: str, limit: int) -> List[Dict[str, Any]]:
    edges = []
    for neighbor in network.graph.neighbors(entity_id):
        data = network.graph.edges[entity_id, neighbor]
        edges.append(
            {
                "id": neighbor,
                "label": network.label_of(neighbor),
                "entity_type": network.type_of(neighbor),
                "weight": int(data.get("weight", 0)),
                "npmi": round(float(data.get("npmi", 0.0)), 4),
                "rescued": bool(data.get("rescued", False)),
            }
        )
    edges.sort(key=lambda item: (-item["weight"], item["id"]))
    return edges[:limit]


def _trajectory(
    temporal: Optional[TemporalBundle], entity_id: str
) -> List[Dict[str, Any]]:
    if temporal is None:
        return []
    points = []
    for slice_ in temporal.slices:
        if slice_.window.id == "all_time":
            continue
        if entity_id in slice_.node_metrics.index:
            row = slice_.node_metrics.loc[entity_id]
            points.append(
                {
                    "epoch": slice_.window.id,
                    "label": slice_.window.label,
                    "start_year": slice_.window.start_year,
                    "end_year": slice_.window.end_year,
                    "active": True,
                    "degree": int(row["degree"]),
                    "betweenness": _float(row["betweenness"]),
                    "burt_constraint": _float(row["burt_constraint"]),
                    "articles": int(row["articles"]),
                }
            )
        else:
            points.append(
                {
                    "epoch": slice_.window.id,
                    "label": slice_.window.label,
                    "start_year": slice_.window.start_year,
                    "end_year": slice_.window.end_year,
                    "active": False,
                    "degree": 0,
                    "betweenness": None,
                    "burt_constraint": None,
                    "articles": 0,
                }
            )
    return points


def _exposure(
    temporal: Optional[TemporalBundle], entity_id: str
) -> Dict[str, Any]:
    """
    Perbandingan eksposur dua epos terakhir.

    Hanya dua epos terakhir yang dibandingkan karena itu pertanyaan yang
    biasanya diajukan ("naik atau turun sekarang?"), dan karena epos lebih awal
    sering kosong untuk entitas yang baru muncul.
    """
    if temporal is None:
        return {"prior_articles": None, "recent_articles": None, "delta": None}

    epochs = [slice_ for slice_ in temporal.slices if slice_.window.id != "all_time"]
    if len(epochs) < 2:
        return {"prior_articles": None, "recent_articles": None, "delta": None}

    recent, prior = epochs[-1], epochs[-2]
    recent_articles = _articles_in(recent, entity_id)
    prior_articles = _articles_in(prior, entity_id)
    return {
        "prior_articles": prior_articles,
        "recent_articles": recent_articles,
        "delta": recent_articles - prior_articles,
    }


def _articles_in(slice_, entity_id: str) -> int:
    if entity_id not in slice_.node_metrics.index:
        return 0
    return int(slice_.node_metrics.at[entity_id, "articles"])


def _sentiment(
    scores: Optional[Mapping[str, Mapping[str, Any]]], entity_id: str
) -> Dict[str, Any]:
    if scores is None:
        return {
            "status": "awaiting_input",
            **{field: None for field in SENTIMENT_FIELDS},
            "stance": None,
        }
    record = scores.get(entity_id)
    if not record:
        return {
            "status": "missing",
            **{field: None for field in SENTIMENT_FIELDS},
            "stance": None,
        }
    pos = _float(record.get("pos"))
    neg = _float(record.get("neg"))
    stance = stance_of(pos, _float(record.get("neu")), neg)
    return {
        "status": "ready",
        "pos": pos,
        "neu": _float(record.get("neu")),
        "neg": neg,
        "confidence": _float(record.get("confidence")),
        "method": record.get("method"),
        "stance": stance,
    }


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    number = float(value)
    if number != number:  # NaN
        return None
    return number

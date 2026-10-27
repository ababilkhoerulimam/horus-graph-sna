"""
Peringkat simpul: broker (betweenness) dan lubang struktural (Burt).

Kedua peringkat memakai kolom yang sudah dihitung di `NetworkBundle`, bukan
menghitung ulang dengan definisi berbeda — itu persis penyebab angka UI pernah
berbeda dari angka artefak.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.build import NetworkBundle
from ..core.metrics import structural_hole_role

AUTONOMY_THRESHOLD = 0.25
CONSTRAINT_THRESHOLD = 0.45


def top_brokers(
    network: NetworkBundle, entity_type: Optional[str] = None, limit: int = 5
) -> List[Dict[str, Any]]:
    """Simpul dengan betweenness tertinggi; `entity_type` menyaring katalog."""
    frame = network.node_metrics
    if entity_type:
        keep = [
            entity_id
            for entity_id in frame.index
            if (network.type_of(entity_id) or "").lower() == entity_type.lower()
        ]
        frame = frame.loc[keep]

    ordered = frame.sort_values(
        ["betweenness", "degree", "entity_id"],
        ascending=[False, False, True],
    ).head(max(0, limit))

    return [
        {
            "rank": rank,
            "id": entity_id,
            "label": network.label_of(entity_id),
            "entity_type": network.type_of(entity_id),
            "betweenness": round(float(row["betweenness"]), 5),
            "degree": int(row["degree"]),
            "community": int(row["louvain_community"]),
        }
        for rank, (entity_id, row) in enumerate(ordered.iterrows(), start=1)
    ]


def sentiment_ranking(
    network: NetworkBundle,
    kind: str = "negative",
    entity_type: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Peringkat entitas menurut persentase sentimen negatif atau positif.

    Entitas tanpa skor terverifikasi tidak ikut diranking. Meranking mereka
    sebagai 0% akan menyamakan "belum diukur" dengan "terukur netral".
    """
    if kind not in ("negative", "positive"):
        raise ValueError("kind harus 'negative' atau 'positive'")

    if network.sentiment is None:
        return {
            "status": "awaiting_input",
            "kind": kind,
            "evaluated": 0,
            "ranking": [],
        }

    field = "neg" if kind == "negative" else "pos"
    rows: List[Dict[str, Any]] = []
    for entity_id, record in network.sentiment.scores.items():
        if entity_type and (network.type_of(entity_id) or "").lower() != entity_type.lower():
            continue
        pos = float(record["pos"])
        neg = float(record["neg"])
        total = pos + float(record["neu"]) + neg
        rows.append(
            {
                "id": entity_id,
                "label": network.label_of(entity_id),
                "entity_type": network.type_of(entity_id),
                "pos": pos,
                "neu": float(record["neu"]),
                "neg": neg,
                "stance": round((pos - neg) / total, 3) if total else None,
                "confidence": record.get("confidence"),
                "method": record.get("method"),
                "degree": int(network.node_metrics.at[entity_id, "degree"])
                if entity_id in network.node_metrics.index
                else 0,
            }
        )

    rows.sort(key=lambda item: (-item[field], -item["degree"], item["id"]))
    ranking = [
        {"rank": rank, **item} for rank, item in enumerate(rows[: max(0, limit)], start=1)
    ]
    return {
        "status": "ready",
        "kind": kind,
        "evaluated": len(rows),
        "ranking": ranking,
    }


def structural_holes(
    network: NetworkBundle, mode: str = "high_autonomy", limit: int = 10
) -> Dict[str, Any]:
    """
    Peringkat Burt.

    `high_autonomy` = constraint terendah (broker yang bebas menjembatani);
    `high_constraint` = tertinggi (simpul yang terkunci dalam clique redundan).
    Constraint yang tidak terhitung dibuang, bukan diisi 0.5.
    """
    if mode not in ("high_autonomy", "high_constraint"):
        raise ValueError("mode harus 'high_autonomy' atau 'high_constraint'")

    frame = network.node_metrics
    frame = frame[frame["burt_constraint"].notna()].copy()
    ascending = mode == "high_autonomy"
    ordered = frame.sort_values(
        ["burt_constraint", "degree", "entity_id"],
        ascending=[ascending, False, True],
    ).head(max(0, limit))

    rows = [
        {
            "id": entity_id,
            "label": network.label_of(entity_id),
            "entity_type": network.type_of(entity_id),
            "burt_constraint": round(float(row["burt_constraint"]), 4),
            "effective_size": None
            if row["effective_size"] is None
            else round(float(row["effective_size"]), 2),
            "degree": int(row["degree"]),
            "role": structural_hole_role(round(float(row["burt_constraint"]), 4)),
        }
        for entity_id, row in ordered.iterrows()
    ]
    return {
        "mode": mode,
        "thresholds": {"autonomy": AUTONOMY_THRESHOLD, "constraint": CONSTRAINT_THRESHOLD},
        "ranking": rows,
    }

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

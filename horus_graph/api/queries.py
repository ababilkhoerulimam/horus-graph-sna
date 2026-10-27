"""
Query baca yang dipakai lebih dari satu jalur.

Endpoint HTTP dan tool copilot harus menjawab dengan angka yang sama persis.
Karena itu perbandingan epos, bukti artikel bersama, dan jaringan topik-aktor
hidup di sini, bukan disalin di masing-masing pemanggil.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .state import AppState


def compare_epochs(left, right) -> Dict[str, Any]:
    """Delta derajat, betweenness, dan constraint antara dua irisan epos."""
    columns = ["degree", "betweenness", "burt_constraint"]
    base = left.node_metrics[columns]
    targ = right.node_metrics[columns]
    joined = base.join(targ, how="outer", suffixes=("_baseline", "_target"))

    gained = sorted(set(targ.index) - set(base.index))
    lost = sorted(set(base.index) - set(targ.index))

    rows: List[Dict[str, Any]] = []
    for entity_id, row in joined.iterrows():
        if entity_id in gained:
            status = "entered"
        elif entity_id in lost:
            status = "exited"
        else:
            status = "persisted"
        rows.append(
            {
                "id": entity_id,
                "status": status,
                "baseline_degree": _int(row.get("degree_baseline")),
                "target_degree": _int(row.get("degree_target")),
                "delta_degree": _delta(row.get("degree_baseline"), row.get("degree_target")),
                "baseline_betweenness": _float(row.get("betweenness_baseline")),
                "target_betweenness": _float(row.get("betweenness_target")),
                "delta_betweenness": _delta(
                    row.get("betweenness_baseline"), row.get("betweenness_target")
                ),
                "baseline_constraint": _float(row.get("burt_constraint_baseline")),
                "target_constraint": _float(row.get("burt_constraint_target")),
                "delta_constraint": _delta(
                    row.get("burt_constraint_baseline"), row.get("burt_constraint_target")
                ),
            }
        )

    ranked = [row for row in rows if row["delta_betweenness"] is not None]
    gainers = sorted(ranked, key=lambda item: -item["delta_betweenness"])[:5]
    losers = sorted(ranked, key=lambda item: item["delta_betweenness"])[:5]

    return {
        "available": True,
        "baseline_period": left.window.id,
        "target_period": right.window.id,
        "nodes_gained": gained,
        "nodes_lost": lost,
        "gained_count": len(gained),
        "lost_count": len(lost),
        "persisted_count": len(set(base.index) & set(targ.index)),
        "top_gainers": gainers,
        "top_losers": losers,
    }


def shared_articles(
    state: AppState, source: str, target: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """Artikel terbaru yang menyebut kedua entitas, sebagai bukti satu relasi."""
    mentions = state.bundle.mentions
    articles = state.bundle.articles
    if mentions.empty or articles.empty:
        return []

    def ids_of(entity_id: str) -> set:
        rows = mentions[mentions["entity_id"].astype(str) == entity_id]
        return set(rows["article_id"].astype(str))

    shared = ids_of(source) & ids_of(target)
    if not shared:
        return []

    subset = articles[articles["article_id"].astype(str).isin(shared)].copy()
    subset["_published"] = pd.to_datetime(
        subset["published_at"], format="ISO8601", utc=True
    )
    subset = subset.sort_values("_published", ascending=False).head(limit)

    return [
        {
            "article_id": str(row["article_id"]),
            "title": row.get("title"),
            "site": row.get("source_id"),
            "published_at": row.get("published_at"),
            "url": row.get("url") if "url" in row.index else None,
        }
        for _, row in subset.iterrows()
    ]


def topic_actor_network(
    state: AppState, topic: Optional[str] = None, min_npmi: float = 0.0
) -> Dict[str, Any]:
    """Jaringan bipartite topik-aktor dengan ambang NPMI."""
    bipartite = state.bipartite
    edges = bipartite.edges
    if not edges.empty:
        edges = edges[edges["npmi"].astype(float) >= min_npmi]
        if topic and topic.upper() != "ALL":
            edges = edges[edges["topic_id"].astype(str) == topic]

    actor_ids = set(edges["entity_id"].astype(str)) if not edges.empty else set()
    topic_ids = set(edges["topic_id"].astype(str)) if not edges.empty else set()

    return {
        "topics": [
            {"id": str(row["topic_id"]), "label": str(row["label"])}
            for _, row in bipartite.topics.iterrows()
            if str(row["topic_id"]) in topic_ids
        ],
        "actors": [
            {
                "id": str(row["entity_id"]),
                "label": str(row["label"]),
                "entity_type": str(row["entity_type"]),
            }
            for _, row in bipartite.actors.iterrows()
            if str(row["entity_id"]) in actor_ids
        ],
        "edges": [
            {
                "topic": str(row["topic_id"]),
                "actor": str(row["entity_id"]),
                "weight": int(row["support"]),
                "npmi": round(float(row["npmi"]), 4),
                "article_count": int(row["actor_articles"]),
            }
            for _, row in edges.iterrows()
        ],
        "total_topics": len(topic_ids),
        "total_actors": len(actor_ids),
        "summary": bipartite.summary(),
    }


def _int(value: Any) -> Optional[int]:
    return None if value is None or pd.isna(value) else int(value)


def _float(value: Any) -> Optional[float]:
    return None if value is None or pd.isna(value) else round(float(value), 6)


def _delta(before: Any, after: Any) -> Optional[float]:
    if before is None or after is None or pd.isna(before) or pd.isna(after):
        return None
    return round(float(after) - float(before), 6)

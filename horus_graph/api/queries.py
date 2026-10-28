"""
Query baca yang dipakai lebih dari satu jalur.

Endpoint HTTP dan tool copilot harus menjawab dengan angka yang sama persis.
Karena itu perbandingan epos, bukti artikel bersama, dan jaringan topik-aktor
hidup di sini, bukan disalin di masing-masing pemanggil.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from ..analysis.resolve import resolve_entity
from ..core import diffusion as diffusion_core
from ..enhance import stats
from .state import AppState


def compare_epochs(left, right, limit: int = 10) -> Dict[str, Any]:
    """
    Delta per simpul dan per sisi antara dua irisan epos.

    Label komunitas Louvain tidak bisa dibandingkan langsung: penomorannya
    sembarang, sehingga "komunitas 2 menjadi 3" sering hanya berarti algoritma
    memulai dari titik lain. Karena itu perpindahan komunitas diukur dengan
    memetakan label baseline ke label target lewat tumpang tindih terbesar, dan
    keseluruhan perubahan diringkas sebagai ARI.
    """
    columns = ["degree", "betweenness", "burt_constraint", "louvain_community"]
    base = left.node_metrics[columns]
    targ = right.node_metrics[columns]
    joined = base.join(targ, how="outer", suffixes=("_baseline", "_target"))

    gained = sorted(set(targ.index) - set(base.index))
    lost = sorted(set(base.index) - set(targ.index))
    persisted = sorted(set(base.index) & set(targ.index))

    mapping, agreement = _community_mapping(base, targ, persisted)

    rows: List[Dict[str, Any]] = []
    for entity_id, row in joined.iterrows():
        if entity_id in gained:
            status = "entered"
        elif entity_id in lost:
            status = "exited"
        else:
            status = "persisted"
        baseline_community = _int(row.get("louvain_community_baseline"))
        target_community = _int(row.get("louvain_community_target"))
        shifted: Optional[bool] = None
        if status == "persisted" and baseline_community is not None and target_community is not None:
            shifted = mapping.get(baseline_community) != target_community
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
                "baseline_community": baseline_community,
                "target_community": target_community,
                "community_shifted": shifted,
            }
        )

    ranked = [row for row in rows if row["delta_betweenness"] is not None]
    gainers = sorted(ranked, key=lambda item: -item["delta_betweenness"])[:limit]
    losers = sorted(ranked, key=lambda item: item["delta_betweenness"])[:limit]

    edges_gained, edges_lost = _edge_diff(left, right, limit)

    return {
        "available": True,
        "baseline_period": left.window.id,
        "target_period": right.window.id,
        "nodes_gained": gained,
        "nodes_lost": lost,
        "gained_count": len(gained),
        "lost_count": len(lost),
        "persisted_count": len(persisted),
        "top_gainers": gainers,
        "top_losers": losers,
        "nodes": rows,
        "community_map": [
            {"baseline": key, "target": value} for key, value in sorted(mapping.items())
        ],
        "community_agreement": agreement,
        "community_shifted_count": sum(1 for row in rows if row["community_shifted"]),
        "edges_gained": edges_gained,
        "edges_lost": edges_lost,
        "edges_gained_count": len(edges_gained),
        "edges_lost_count": len(edges_lost),
    }


def _community_mapping(
    base: pd.DataFrame, targ: pd.DataFrame, persisted: List[str]
) -> tuple[Dict[int, int], Optional[float]]:
    """
    Peta label komunitas baseline → target, dan ARI kedua partisi.

    Pemetaan memakai tumpang tindih terbesar; ARI dipakai sebagai ringkasan
    karena ia tidak bergantung pada penomoran sama sekali.
    """
    if not persisted:
        return {}, None

    baseline_labels = [int(base.loc[entity_id, "louvain_community"]) for entity_id in persisted]
    target_labels = [int(targ.loc[entity_id, "louvain_community"]) for entity_id in persisted]

    overlap: Dict[int, Dict[int, int]] = {}
    for baseline_label, target_label in zip(baseline_labels, target_labels, strict=True):
        counts = overlap.setdefault(baseline_label, {})
        counts[target_label] = counts.get(target_label, 0) + 1

    mapping = {
        baseline_label: max(counts.items(), key=lambda item: (item[1], -item[0]))[0]
        for baseline_label, counts in overlap.items()
    }
    agreement = round(
        float(stats.adjusted_rand_index(baseline_labels, target_labels)), 4
    )
    return mapping, agreement


def _edge_diff(left, right, limit: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Sisi yang muncul dan hilang, diurutkan menurut support di epos tujuannya."""
    before = _edge_index(left)
    after = _edge_index(right)

    def rows(keys, index) -> List[Dict[str, Any]]:
        items = [
            {"source": key[0], "target": key[1],
             "support": index[key][0], "npmi": index[key][1]}
            for key in keys
        ]
        items.sort(key=lambda item: (-(item["support"] or 0), item["source"], item["target"]))
        return items[:limit]

    return rows(sorted(set(after) - set(before)), after), rows(
        sorted(set(before) - set(after)), before
    )


def _edge_index(slice_) -> Dict[tuple, tuple]:
    edges = getattr(slice_, "edges", None)
    if edges is None or edges.empty:
        return {}
    index: Dict[tuple, tuple] = {}
    for _, row in edges.iterrows():
        source, target = str(row["source"]), str(row["target"])
        key = (source, target) if source <= target else (target, source)
        support = row.get("support")
        npmi = row.get("npmi")
        index[key] = (
            None if support is None or pd.isna(support) else int(support),
            None if npmi is None or pd.isna(npmi) else round(float(npmi), 4),
        )
    return index


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


def diffusion(
    state: AppState,
    seeds: List[str],
    *,
    model: str = "ic",
    probability: float = 0.1,
    threshold: float = 0.2,
    runs: int = 200,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Sebaran difusi dari satu set simpul penyebar.

    Difusi tidak dihitung saat build: masukannya — siapa penyebarnya dan
    berapa kali disimulasikan — datang dari pemakai, jadi blok bootstrap-nya
    akan selalu kosong dan hanya menambah derau. Karena itu ia dihitung per
    permintaan, seperti kontrafaktual.

    Nama penyebar diterima seperti yang diketik pengguna dan diselesaikan
    lewat `resolve_entity` yang sama dengan jalur lain, supaya "egy" dan
    "Egy Maulana" tidak menghasilkan dua jawaban berbeda.
    """
    network = state.network
    graph = network.graph
    if graph.number_of_edges() == 0:
        return diffusion_core.awaiting("Graf tanpa sisi: tidak ada jalur penularan.")
    if not seeds:
        return diffusion_core.awaiting("Difusi butuh setidaknya satu simpul penyebar (seed).")

    resolved: List[str] = []
    unknown: List[str] = []
    for query in seeds:
        entity_id = resolve_entity(network, query)
        if entity_id is None:
            unknown.append(query)
        elif entity_id not in resolved:
            resolved.append(entity_id)
    if unknown:
        raise ValueError(f"Simpul penyebar tidak ditemukan: {', '.join(sorted(unknown))}.")

    if model == "threshold":
        result = diffusion_core.linear_threshold(
            graph, resolved, threshold=threshold, runs=runs, seed=seed
        )
    else:
        result = diffusion_core.independent_cascade(
            graph, resolved, probability=probability, runs=runs, seed=seed
        )

    result["seeds"] = [
        {"id": entity_id, "label": network.label_of(entity_id), "entity_type": network.type_of(entity_id)}
        for entity_id in resolved
    ]
    adopters = [
        {
            "id": row["id"],
            "label": network.label_of(row["id"]),
            "entity_type": network.type_of(row["id"]),
            "frequency": row["frequency"],
        }
        for row in result["adoption_frequency"]
    ]
    adopters.sort(key=lambda row: (-row["frequency"], row["id"]))
    result["adoption_frequency"] = adopters
    return result

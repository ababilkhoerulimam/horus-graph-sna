"""Endpoint HTTP. Semua handler membaca satu `AppState` yang sama."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

from ..analysis import (
    entity_dossier,
    executive_briefing,
    simulate_removal,
    structural_holes,
    top_brokers,
    trace_path,
)
from ..enhance import (
    bootstrap_network,
    degree_preserving_null,
    detect_bursts,
    epoch_turnover,
    topology_profile,
)
from ..presentation import Presentation
from . import serializers
from .state import AppState, BundleNotFound, get_state

router = APIRouter()


def _state(request: Request) -> AppState:
    try:
        return get_state(request.app.state.bundle_path)
    except BundleNotFound as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # bundle rusak: jangan sembunyikan sebagai 500 kosong
        raise HTTPException(status_code=503, detail=f"Bundle gagal dimuat: {exc}") from exc


# --- dasar -----------------------------------------------------------------


@router.get("/api/health")
def health(request: Request) -> Dict[str, Any]:
    state = _state(request)
    summary = state.network.summary
    return {
        "status": "ok",
        "dataset": state.bundle.manifest.dataset_id,
        "nodes": summary["nodes"],
        "edges": summary["edges"],
        "density": summary["density"],
        "contract_version": serializers.contract_version(),
        "build_seconds": state.build_seconds,
    }


@router.get("/api/dataset/status")
def dataset_status(request: Request) -> Dict[str, Any]:
    state = _state(request)
    return {
        "dataset": state.bundle.manifest.dataset_id,
        "counts": dict(state.bundle.manifest.counts),
        "layers": dict(state.network.layers),
        "root": str(state.root),
        "build_seconds": state.build_seconds,
    }


@router.get("/api/bootstrap")
def bootstrap(request: Request) -> Dict[str, Any]:
    return serializers.bootstrap_payload(_state(request))


@router.get("/api/provenance")
def provenance(request: Request) -> Dict[str, Any]:
    return serializers.bootstrap_payload(_state(request))["provenance"]


# --- graf ------------------------------------------------------------------


@router.get("/api/graph/overview")
def graph_overview(request: Request) -> Dict[str, Any]:
    state = _state(request)
    summary = state.network.summary
    presentation: Presentation = state.presentation
    return {
        "title": presentation.title,
        "subtitle": presentation.subtitle,
        "ego_node": presentation.ego.id if presentation.ego else None,
        "ego_label": presentation.ego.label if presentation.ego else None,
        "total_nodes": summary["nodes"],
        "total_edges": summary["edges"],
        "density": summary["density"],
        "communities_count": summary["communities"]["count"],
        "community_sizes": summary["communities"]["sizes"],
        "modularity": summary["communities"]["modularity"],
        "transitivity": summary["transitivity"],
        "diameter": summary["diameter"],
        "average_path_length": summary["average_path_length"],
        "components": summary["components"],
        "isolated": summary["isolated"],
    }


@router.get("/api/graph/compare")
def graph_compare(
    request: Request,
    baseline: Optional[str] = None,
    target: Optional[str] = None,
) -> Dict[str, Any]:
    state = _state(request)
    slices = [item for item in state.temporal.slices if item.window.id != "all_time"]
    if len(slices) < 2:
        return {
            "baseline_period": None,
            "target_period": None,
            "available": False,
            "message": "Perlu minimal dua epos untuk membandingkan.",
        }

    ids = [item.window.id for item in slices]
    baseline = baseline or ids[0]
    target = target or ids[-1]
    if baseline not in ids or target not in ids:
        raise HTTPException(
            status_code=400, detail=f"Epos tidak dikenal. Pilihan: {', '.join(ids)}"
        )

    return _compare(state.temporal.by_id(baseline), state.temporal.by_id(target))


def _compare(left, right) -> Dict[str, Any]:
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


def _int(value: Any) -> Optional[int]:
    return None if value is None or pd.isna(value) else int(value)


def _float(value: Any) -> Optional[float]:
    return None if value is None or pd.isna(value) else round(float(value), 6)


def _delta(before: Any, after: Any) -> Optional[float]:
    if before is None or after is None or pd.isna(before) or pd.isna(after):
        return None
    return round(float(after) - float(before), 6)


# --- entitas ---------------------------------------------------------------


@router.get("/api/entities")
def entities(request: Request) -> Dict[str, Any]:
    return {"entities": serializers.entity_index(_state(request))}


@router.get("/api/entities/{entity_id:path}")
def entity(request: Request, entity_id: str) -> Dict[str, Any]:
    state = _state(request)
    try:
        return entity_dossier(state.network, entity_id, temporal=state.temporal)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --- analisis --------------------------------------------------------------


@router.get("/api/analysis/path")
def analysis_path(request: Request, origin: str, target: str) -> Dict[str, Any]:
    return trace_path(_state(request).network, origin, target)


@router.get("/api/analysis/counterfactual")
def analysis_counterfactual(request: Request, entity: str) -> Dict[str, Any]:
    return simulate_removal(_state(request).network, entity)


@router.get("/api/analysis/brokers")
def analysis_brokers(
    request: Request, entity_type: Optional[str] = None, limit: int = 5
) -> Dict[str, Any]:
    ranking = top_brokers(_state(request).network, entity_type=entity_type, limit=limit)
    return {"entity_type": entity_type, "ranking": ranking}


@router.get("/api/analysis/holes")
def analysis_holes(
    request: Request, mode: str = "high_autonomy", limit: int = 10
) -> Dict[str, Any]:
    return structural_holes(_state(request).network, mode=mode, limit=limit)


@router.get("/api/analysis/briefing")
def analysis_briefing(request: Request) -> Dict[str, Any]:
    state = _state(request)
    return executive_briefing(
        state.network,
        temporal=state.temporal,
        anomaly=state.anomaly,
        bipartite=state.bipartite,
    )


# --- bukti -----------------------------------------------------------------


@router.get("/api/edges/evidence")
def edge_evidence(
    request: Request,
    source: str,
    target: str,
    limit: int = Query(default=5, ge=1, le=50),
) -> Dict[str, Any]:
    state = _state(request)
    network = state.network
    if not network.graph.has_edge(source, target):
        raise HTTPException(status_code=404, detail="Edge tidak ada di jaringan.")

    data = network.graph.edges[source, target]
    articles = _shared_articles(state, source, target, limit)
    return {
        "source": source,
        "target": target,
        "weight": int(data.get("weight", 0)),
        "npmi": serializers._num(data.get("npmi")),
        "rescued": bool(data.get("rescued", False)),
        "evidence": articles,
    }


def _shared_articles(state: AppState, source: str, target: str, limit: int) -> List[Dict[str, Any]]:
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

    result = []
    for _, row in subset.iterrows():
        result.append(
            {
                "article_id": str(row["article_id"]),
                "title": row.get("title"),
                "site": row.get("source_id"),
                "published_at": row.get("published_at"),
                "url": row.get("url") if "url" in row.index else None,
            }
        )
    return result


# --- topik -----------------------------------------------------------------


@router.get("/api/topics/actor-network")
def topic_actor_network(
    request: Request, topic: Optional[str] = None, min_npmi: float = 0.0
) -> Dict[str, Any]:
    state = _state(request)
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


# --- temporal & enhance ----------------------------------------------------


@router.get("/api/temporal")
def temporal(request: Request) -> Dict[str, Any]:
    return {"epochs": serializers.epoch_payloads(_state(request))}


@router.get("/api/enhance")
def enhance(
    request: Request,
    resamples: int = Query(default=100, ge=10, le=1000),
    bootstrap_resamples: int = Query(default=50, ge=10, le=500),
    seed: int = 42,
) -> Dict[str, Any]:
    state = _state(request)
    network = state.network
    null = degree_preserving_null(network, resamples=resamples, seed=seed)
    boot = bootstrap_network(network, resamples=bootstrap_resamples, seed=seed)
    return {
        "null_model": null.as_dict(),
        "bootstrap": {
            "ari": boot.ari,
            "betweenness": boot.betweenness.reset_index().to_dict(orient="records"),
            "resamples": boot.resamples,
        },
        "topology": topology_profile(network).as_dict(),
        "turnover": {
            "transitions": epoch_turnover(state.temporal).to_dict(orient="records"),
        },
        "bursts": detect_bursts(state.bundle).as_dict(),
    }

"""Endpoint HTTP. Semua handler membaca satu `AppState` yang sama."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..analysis import (
    entity_dossier,
    executive_briefing,
    simulate_removal,
    structural_holes,
    top_brokers,
    trace_path,
)
from ..copilot.llm import llm_available
from ..enhance.reporting import reporting_block
from ..export import formats as export_formats
from ..presentation import Presentation
from . import queries, schemas, serializers
from .auth import require_token
from .datasets import list_snapshots
from .state import AppState, BundleNotFound, get_state

logger = logging.getLogger(__name__)

# Semua endpoint data tunduk pada satu pemeriksaan token. Tanpa
# `HORUS_API_TOKEN`, pemeriksaan itu tidak melakukan apa pun.
router = APIRouter(dependencies=[Depends(require_token)])



def _state(request: Request) -> AppState:
    try:
        return get_state(request.app.state.bundle_path)
    except BundleNotFound as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # Detail teknis (path, traceback) hanya ke log. Klien mendapat pesan
        # yang sama untuk semua kegagalan muat, supaya isi disk tidak bocor
        # lewat respons error.
        logger.exception("Bundle gagal dimuat: %s", request.app.state.bundle_path)
        raise HTTPException(
            status_code=503,
            detail="Bundle gagal dimuat. Periksa log server untuk detailnya.",
        ) from exc


# --- dasar -----------------------------------------------------------------


@router.get("/api/health", response_model=schemas.HealthResponse)
def health(request: Request) -> Dict[str, Any]:
    state = _state(request)
    summary = state.network.summary
    return {
        "status": "ok",
        "dataset": state.bundle.manifest.dataset_id,
        "snapshot_id": state.bundle.manifest.snapshot_id,
        "nodes": summary["nodes"],
        "edges": summary["edges"],
        "density": summary["density"],
        "contract_version": serializers.contract_version(),
        "build_seconds": state.build_seconds,
        # `copilot` menyala karena drawer selalu punya jalur deterministik.
        # `llm` menandai apakah jawaban bebas juga tersedia.
        "capabilities": {"copilot": True, "llm": llm_available()},
    }


@router.get("/api/datasets", response_model=schemas.DatasetListResponse)
def datasets(request: Request) -> Dict[str, Any]:
    """Snapshot yang tersedia di folder induk bundle aktif. Read-only."""
    state = _state(request)
    return {
        "active": state.bundle.manifest.snapshot_id,
        "datasets": list_snapshots(state.root.parent),
    }


@router.get("/api/dataset/status", response_model=schemas.DatasetStatusResponse)
def dataset_status(request: Request) -> Dict[str, Any]:
    state = _state(request)
    return {
        "dataset": state.bundle.manifest.dataset_id,
        "counts": dict(state.bundle.manifest.counts),
        "layers": dict(state.network.layers),
        # Nama folder saja: path absolut membocorkan susunan disk ke klien.
        "root": state.root.name,
        "build_seconds": state.build_seconds,
    }


@router.get("/api/bootstrap")
def bootstrap(request: Request) -> Dict[str, Any]:
    return serializers.bootstrap_payload(_state(request))


@router.get("/api/provenance")
def provenance(request: Request) -> Dict[str, Any]:
    # `bootstrap_payload` merakit 140 KB payload untuk mengambil satu blok;
    # blok itu sendiri murah, jadi panggil langsung.
    state = _state(request)
    return reporting_block(state.bundle, state.network, seed=serializers.PROVENANCE_SEED)


# --- graf ------------------------------------------------------------------


@router.get("/api/graph/overview", response_model=schemas.GraphOverviewResponse)
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


@router.get("/api/graph/key-events", response_model=List[schemas.KeyEvent])
def key_events(request: Request) -> List[Dict[str, Any]]:
    """
    Lonjakan volume bulanan sebagai penanda peristiwa pada timeline.

    UI memakai ini untuk menaruh pin di slider; aktor terkait sengaja kosong
    karena anomali dihitung dari korpus, bukan dari graf.
    """
    state = _state(request)
    label = state.presentation.labels.get("articles", "artikel")
    return [
        {
            "date": f"{spike['period']}-01",
            "title": f"{spike['article_count']} {label}",
            "description": f"z = {float(spike['z_score']):.2f} ({spike.get('severity', '')})",
            "severity": spike.get("severity"),
            "related_actors": [],
        }
        for spike in state.anomaly.spikes
    ]


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

    return queries.compare_epochs(
        state.temporal.by_id(baseline), state.temporal.by_id(target)
    )


# --- entitas ---------------------------------------------------------------


@router.get("/api/entities", response_model=schemas.EntityIndexResponse)
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


@router.get("/api/analysis/brokers", response_model=schemas.BrokerRankingResponse)
def analysis_brokers(
    request: Request,
    entity_type: Optional[str] = None,
    limit: int = Query(default=5, ge=1, le=100),
) -> Dict[str, Any]:
    ranking = top_brokers(_state(request).network, entity_type=entity_type, limit=limit)
    return {"entity_type": entity_type, "ranking": ranking}


@router.get("/api/analysis/holes", response_model=schemas.HoleRankingResponse)
def analysis_holes(
    request: Request,
    mode: str = "high_autonomy",
    limit: int = Query(default=10, ge=1, le=100),
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


@router.get("/api/edges/evidence", response_model=schemas.EdgeEvidenceResponse)
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
    articles = queries.shared_articles(state, source, target, limit)
    return {
        "source": source,
        "target": target,
        "weight": int(data.get("weight", 0)),
        "npmi": serializers._num(data.get("npmi")),
        "rescued": bool(data.get("rescued", False)),
        "evidence": articles,
    }


# --- topik -----------------------------------------------------------------


@router.get("/api/topics/actor-network")
def topic_actor_network(
    request: Request,
    topic: Optional[str] = None,
    min_npmi: float = Query(default=0.0, ge=-1.0, le=1.0),
) -> Dict[str, Any]:
    return queries.topic_actor_network(_state(request), topic=topic, min_npmi=min_npmi)


# --- temporal --------------------------------------------------------------


@router.get("/api/temporal", response_model=schemas.TemporalResponse)
def temporal(request: Request) -> Dict[str, Any]:
    return {"epochs": serializers.epoch_payloads(_state(request))}


# --- ekspor ----------------------------------------------------------------


@router.get("/api/export/{fmt}")
def export_network(request: Request, fmt: str) -> Response:
    """Unduh jaringan sebagai GraphML, GEXF, atau CSV."""
    state = _state(request)
    try:
        body = export_formats.render(state.network, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    name = f"{state.bundle.manifest.dataset_id}.{export_formats.EXTENSIONS[fmt]}"
    return Response(
        content=body,
        media_type=export_formats.CONTENT_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )

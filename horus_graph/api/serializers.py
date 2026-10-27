"""
Bentuk data yang dikirim ke visualizer.

Satu tempat untuk mengubah dict engine menjadi JSON siap-pakai. Tidak ada nama
domain di sini: label, warna, dan deskripsi datang dari `Presentation`, bukan
dari konstanta di file ini.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd

from ..contract import schema
from ..core.build import NetworkBundle
from ..enhance.reporting import reporting_block
from ..presentation import Presentation
from .state import AppState

ROUND = 4


def bootstrap_payload(state: AppState) -> Dict[str, Any]:
    """Seluruh data yang dibutuhkan visualizer untuk boot, dalam satu panggilan."""
    network = state.network
    presentation = state.presentation
    block = reporting_block(state.bundle, network, seed=42)

    return {
        "presentation": presentation.as_dict(),
        "dataset": {
            "id": state.bundle.manifest.dataset_id,
            "title": presentation.title,
            "subtitle": presentation.subtitle,
            "snapshot_at": state.bundle.manifest.snapshot_at.isoformat(),
            "date_range": [
                str(state.bundle.manifest.date_range.start),
                str(state.bundle.manifest.date_range.end),
            ],
            "timezone": state.bundle.manifest.timezone,
            "counts": dict(state.bundle.manifest.counts),
            "layers": dict(network.layers),
            "build_seconds": state.build_seconds,
        },
        "graph": {
            "nodes": node_payloads(state),
            "links": link_payloads(network),
            "summary": dict(network.summary),
            "communities": community_payloads(network, presentation),
        },
        "epochs": epoch_payloads(state),
        "topics": topic_payloads(state),
        "entity_index": entity_index(state),
        "coverage": coverage_payload(state),
        "anomaly": anomaly_payload(state),
        "provenance": block,
    }


def node_payloads(state: AppState) -> List[Dict[str, Any]]:
    network = state.network
    presentation = state.presentation
    entities = state.bundle.entities
    catalog = entities.set_index(entities["entity_id"].astype(str))
    years = entity_years(state)

    nodes: List[Dict[str, Any]] = []
    for index, (entity_id, row) in enumerate(network.node_metrics.iterrows()):
        entry = catalog.loc[entity_id] if entity_id in catalog.index else None
        entity_type = _text(_pick(entry, "entity_type")) or network.type_of(entity_id)
        cluster = _text(_pick(entry, "cluster"))
        first_year, active_years = years.get(entity_id, (None, []))

        nodes.append(
            {
                "id": entity_id,
                "label": network.label_of(entity_id),
                "display_label": network.label_of(entity_id),
                "entity_type": entity_type,
                "color": _text(_pick(entry, "color"))
                or presentation.color_for(entity_type, index),
                "cluster": cluster,
                "cluster_label": _cluster_label(presentation, cluster),
                "sector": _text(_pick(entry, "sector")),
                "description": _text(_pick(entry, "description")),
                "tier": _int(_pick(entry, "tier")),
                "ring_level": _int(_pick(entry, "ring_level")),
                "orbit_label": presentation.orbit_label(_int(_pick(entry, "ring_level"))),
                "is_anchor": _bool(_pick(entry, "is_anchor")),
                "is_ego": presentation.ego is not None
                and presentation.ego.id == entity_id,
                "articles": int(row["articles"]),
                "degree": int(row["degree"]),
                "pagerank": _num(row["pagerank"]),
                "betweenness": _num(row["betweenness"]),
                "closeness": _num(row["closeness"]),
                "burt_constraint": _num(row["burt_constraint"]),
                "effective_size": _num(row["effective_size"]),
                "structural_hole_role": row["structural_hole_role"],
                "community": int(row["louvain_community"]),
                "first_seen_year": first_year,
                "active_years": active_years,
            }
        )
    return nodes


def link_payloads(network: NetworkBundle) -> List[Dict[str, Any]]:
    cooc = network.cooccurrence
    position = {entity_id: index for index, entity_id in enumerate(cooc.entity_ids)}
    volume = cooc.node_articles

    links: List[Dict[str, Any]] = []
    for source, target, data in network.graph.edges(data=True):
        support = int(data.get("weight", 0))
        i, j = position[source], position[target]
        n_u, n_v = int(volume[i]), int(volume[j])
        links.append(
            {
                "source": source,
                "target": target,
                "weight": support,
                "npmi": _num(data.get("npmi")),
                "jaccard": _ratio(support, n_u + n_v - support),
                "salton_cosine": _ratio(support, math.sqrt(n_u * n_v)),
                "rescued": bool(data.get("rescued", False)),
            }
        )
    links.sort(key=lambda item: (-item["weight"], item["source"], item["target"]))
    return links


def community_payloads(
    network: NetworkBundle, presentation: Presentation
) -> List[Dict[str, Any]]:
    sizes: Dict[int, int] = {}
    for community_id in network.communities.values():
        sizes[int(community_id)] = sizes.get(int(community_id), 0) + 1

    colors = presentation.palette.community
    result = []
    for order, community_id in enumerate(sorted(sizes)):
        result.append(
            {
                "id": community_id,
                "size": sizes[community_id],
                "label": f"{presentation.label('community')} {community_id}",
                "color": colors[order % len(colors)] if colors else None,
            }
        )
    return result


def epoch_payloads(state: AppState) -> List[Dict[str, Any]]:
    result = []
    for slice_ in state.temporal.slices:
        result.append(
            {
                "id": slice_.window.id,
                "label": slice_.window.label,
                "start_year": slice_.window.start_year,
                "end_year": slice_.window.end_year,
                "nodes": slice_.graph.number_of_nodes(),
                "edges": slice_.graph.number_of_edges(),
                "density": slice_.density,
                "articles": slice_.articles,
                "isolated": list(slice_.isolated),
                "top_broker": slice_.top_broker,
                "top_autonomy": slice_.top_autonomy,
                "narrative": state.presentation.epoch_narratives.get(
                    str(slice_.window.start_year)
                ),
            }
        )
    return result


def topic_payloads(state: AppState) -> List[Dict[str, Any]]:
    frame = state.bundle.topics
    if frame.empty:
        return []
    result = []
    for _, row in frame.iterrows():
        keywords = row.get("keywords")
        result.append(
            {
                "id": str(row["topic_id"]),
                "label": str(row["label"]),
                "keywords": [str(value) for value in keywords]
                if isinstance(keywords, (list, tuple))
                else [],
            }
        )
    return result


def entity_index(state: AppState) -> List[Dict[str, Any]]:
    frame = state.bundle.entities
    if frame.empty:
        return []
    result = []
    for _, row in frame.iterrows():
        aliases = row.get("aliases")
        result.append(
            {
                "id": str(row["entity_id"]),
                "label": str(row["label"]),
                "entity_type": str(row["entity_type"]),
                "aliases": [str(value) for value in aliases]
                if isinstance(aliases, (list, tuple))
                else [],
            }
        )
    return result


def coverage_payload(state: AppState) -> Dict[str, Any]:
    articles = state.bundle.articles
    if articles.empty:
        return {"articles": 0, "dated": 0, "sources": 0, "first": None, "last": None}

    published = pd.to_datetime(articles["published_at"], format="ISO8601", utc=True)
    return {
        "articles": int(len(articles)),
        "dated": int(published.notna().sum()),
        "sources": int(articles["source_id"].astype(str).nunique()),
        "first": published.min().date().isoformat() if published.notna().any() else None,
        "last": published.max().date().isoformat() if published.notna().any() else None,
        "entities": int(len(state.bundle.entities)),
        "mentions": int(len(state.bundle.mentions)),
        "topics": int(len(state.bundle.topics)),
    }


def anomaly_payload(state: AppState) -> Dict[str, Any]:
    report = state.anomaly
    return {
        "months": report.months,
        "partial_periods": list(report.partial_periods),
        "spikes": [dict(spike) for spike in report.spikes],
        "series": [
            {"period": str(period), "articles": int(count)}
            for period, count in report.monthly_counts.items()
        ],
    }


def entity_years(state: AppState) -> Dict[str, Tuple[Optional[int], List[int]]]:
    """Tahun pertama dan daftar tahun aktif per entitas, dari artikel bertanggal."""
    articles = state.bundle.articles
    mentions = state.bundle.mentions
    if articles.empty or mentions.empty:
        return {}

    published = pd.to_datetime(articles["published_at"], format="ISO8601", utc=True)
    year_of = dict(
        zip(articles["article_id"].astype(str), published.dt.year.astype("Int64"))
    )
    pairs = mentions[["article_id", "entity_id"]].astype(str).drop_duplicates()
    pairs["year"] = pairs["article_id"].map(year_of)
    pairs = pairs.dropna(subset=["year"])

    result: Dict[str, Tuple[Optional[int], List[int]]] = {}
    for entity_id, group in pairs.groupby("entity_id")["year"]:
        years = sorted({int(value) for value in group})
        result[str(entity_id)] = (years[0] if years else None, years)
    return result


def _cluster_label(presentation: Presentation, cluster: Optional[str]) -> Optional[str]:
    if not cluster:
        return None
    style = presentation.clusters.get(cluster)
    return style.label if style and style.label else cluster


def _pick(row: Optional[pd.Series], column: str) -> Any:
    if row is None or column not in row.index:
        return None
    return row[column]


def _missing(value: Any) -> bool:
    """None, NaN, dan pd.NA dianggap tidak ada; list tidak pernah dianggap kosong."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _text(value: Any) -> Optional[str]:
    if _missing(value):
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> Optional[int]:
    if _missing(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if _missing(value):
        return False
    return bool(value)


def _num(value: Any) -> Optional[float]:
    if _missing(value):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, ROUND)


def _ratio(numerator: float, denominator: float) -> Optional[float]:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), ROUND)


def contract_version() -> str:
    return schema.CONTRACT_VERSION

"""
Irisan temporal per epos.

Setiap epos dihitung ulang dari artikel pada rentang tahunnya sendiri — bukan
graf global yang diskalakan dengan faktor. Konsekuensinya angka epos bisa naik
turun dengan sendirinya: epos dengan korpus tipis boleh punya densitas lebih
tinggi tanpa berarti jaringannya "lebih padat" secara substantif.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd

from ..io.bundle import DataBundle
from . import metrics
from .backbone import BackboneConfig, select_edges
from .cooccurrence import cooccurrence, edge_years


@dataclass(frozen=True)
class EpochWindow:
    id: str
    label: str
    start_year: int
    end_year: int

    def contains(self, year: int) -> bool:
        return self.start_year <= year <= self.end_year


@dataclass(frozen=True)
class EpochSlice:
    """Subgraf satu epos. Simpul tanpa edge dibuang, bukan dibiarkan menggantung."""

    window: EpochWindow
    graph: nx.Graph
    node_metrics: pd.DataFrame
    edges: pd.DataFrame
    density: float
    articles: int
    isolated: Tuple[str, ...]
    top_broker: Optional[Dict[str, Any]]
    top_autonomy: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class TemporalBundle:
    slices: Tuple[EpochSlice, ...]
    total_articles: int
    year_span: Tuple[int, int]

    def by_id(self, epoch_id: str) -> EpochSlice:
        for slice_ in self.slices:
            if slice_.window.id == epoch_id:
                return slice_
        raise KeyError(epoch_id)


def article_years(bundle: DataBundle) -> np.ndarray:
    """Tahun setiap baris `articles`, sejajar dengan urutan tabelnya."""
    if bundle.articles.empty:
        return np.zeros(0, dtype=np.int64)
    published = pd.to_datetime(bundle.articles["published_at"], format="ISO8601", utc=True)
    return published.dt.year.fillna(0).astype(np.int64).to_numpy()


def build_temporal(
    bundle: DataBundle,
    config: Optional[BackboneConfig] = None,
    include_all_time: bool = True,
) -> TemporalBundle:
    """Hitung satu subgraf per epos di `domain.epochs`, plus agregat all-time."""
    if not bundle.domain.epochs:
        # Dataset tanpa jendela epos tetap sah: lapisan temporal kosong, bukan
        # alasan menolak seluruh bundle.
        return TemporalBundle(slices=(), total_articles=len(bundle.articles), year_span=(0, 0))

    config = config or BackboneConfig(rescue_isolated=False)
    years = article_years(bundle)
    article_ids = bundle.articles["article_id"].astype(str).to_numpy()

    windows: List[EpochWindow] = [
        EpochWindow(epoch.id, epoch.label, epoch.start_year, epoch.end_year)
        for epoch in bundle.domain.epochs
    ]
    if include_all_time:
        span = bundle.domain.epochs
        windows.append(
            EpochWindow(
                "all_time",
                f"All-Time ({span[0].start_year}-{span[-1].end_year}): Agregat Multi-Tahun",
                span[0].start_year,
                span[-1].end_year,
            )
        )

    slices = []
    for window in windows:
        mask = (years >= window.start_year) & (years <= window.end_year)
        subset = bundle.subset(article_ids[mask])
        slices.append(_slice(window, subset, years[mask], config))

    start = min(window.start_year for window in windows)
    end = max(window.end_year for window in windows)
    return TemporalBundle(
        slices=tuple(slices),
        total_articles=len(bundle.articles),
        year_span=(int(start), int(end)),
    )


def _slice(
    window: EpochWindow,
    subset: DataBundle,
    years: np.ndarray,
    config: BackboneConfig,
) -> EpochSlice:
    cooc = cooccurrence(subset)
    selected, _, _ = select_edges(cooc, config)

    graph = nx.Graph()
    for position in selected:
        u = cooc.entity_ids[int(cooc.pair_u[position])]
        v = cooc.entity_ids[int(cooc.pair_v[position])]
        graph.add_edge(u, v, weight=int(cooc.support[position]), npmi=float(cooc.npmi[position]))

    # Simpul tanpa edge dibuang supaya densitas tidak dihitung dari aktor yatim.
    present = {cooc.entity_ids[i] for i in range(len(cooc.entity_ids)) if cooc.node_articles[i] > 0}
    isolated = tuple(sorted(present - set(graph.nodes)))

    support_years = edge_years(cooc, years, selected)
    edge_rows = []
    for position in selected:
        u = cooc.entity_ids[int(cooc.pair_u[position])]
        v = cooc.entity_ids[int(cooc.pair_v[position])]
        edge_rows.append(
            {
                "source": u,
                "target": v,
                "support": int(cooc.support[position]),
                "npmi": round(float(cooc.npmi[position]), 4),
                "years": tuple(support_years.get(int(position), ())),
            }
        )
    edges = pd.DataFrame(
        edge_rows, columns=["source", "target", "support", "npmi", "years"]
    ).sort_values(["support", "source", "target"], ascending=[False, True, True], ignore_index=True)

    node_metrics = _node_metrics(graph, cooc)
    return EpochSlice(
        window=window,
        graph=graph,
        node_metrics=node_metrics,
        edges=edges,
        density=metrics.density(graph.number_of_edges(), graph.number_of_nodes()),
        articles=len(subset.articles),
        isolated=isolated,
        top_broker=_top_broker(node_metrics),
        top_autonomy=_top_autonomy(node_metrics),
    )


def _node_metrics(graph: nx.Graph, cooc) -> pd.DataFrame:
    if graph.number_of_nodes() == 0:
        return pd.DataFrame(
            columns=["degree", "betweenness", "burt_constraint", "effective_size", "articles"]
        )
    betweenness = metrics.betweenness(graph)
    constraint = metrics.constraint(graph)
    effective = metrics.effective_size(graph)
    articles = {cooc.entity_ids[i]: int(cooc.node_articles[i]) for i in range(len(cooc.entity_ids))}

    rows = []
    for node in sorted(graph.nodes):
        burt = constraint.get(node)
        rows.append(
            {
                "entity_id": node,
                "degree": int(graph.degree(node)),
                "betweenness": round(float(betweenness.get(node, 0.0)), 6),
                "burt_constraint": None if burt is None else round(float(burt), 4),
                "effective_size": None if effective.get(node) is None else round(float(effective[node]), 2),
                "articles": articles.get(node, 0),
            }
        )
    return pd.DataFrame(rows).set_index("entity_id")


def _top_broker(node_metrics: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if node_metrics.empty:
        return None
    node = node_metrics["betweenness"].idxmax()
    return {"id": node, "betweenness": float(node_metrics.at[node, "betweenness"])}


def _top_autonomy(node_metrics: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if node_metrics.empty:
        return None
    candidates = node_metrics[node_metrics["burt_constraint"].notna()]
    if candidates.empty:
        return None
    node = candidates["burt_constraint"].idxmin()
    return {"id": node, "burt_constraint": float(candidates.at[node, "burt_constraint"])}

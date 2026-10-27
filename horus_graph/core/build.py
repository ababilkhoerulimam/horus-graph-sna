"""
Perakitan jaringan dari bundle: co-occurrence -> backbone -> metrik.

Tidak ada IO di modul ini. Semua masukan datang dari `DataBundle`, semua
keluaran berupa objek immutable, sehingga pemanggil bisa menyimpan hasilnya ke
format apa pun (artefak UI, parquet, API) tanpa engine ikut tahu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

import networkx as nx
import pandas as pd

from .._coerce import to_number
from ..contract.models import Domain
from ..io.bundle import DataBundle
from . import metrics
from .backbone import BackboneConfig, BackboneReport, select_edges
from .cooccurrence import Cooccurrence, cooccurrence
from .layers import SentimentLayer, TransmissionLayer, sentiment_layer, transmission_layer


@dataclass(frozen=True)
class NetworkBundle:
    """Jaringan yang sudah dibangun beserta semua angka turunannya."""

    graph: nx.Graph
    entity_ids: Tuple[str, ...]
    entities: pd.DataFrame
    domain: Domain
    layers: Mapping[str, str]
    transmission: Optional[TransmissionLayer]
    sentiment: Optional[SentimentLayer]
    total_articles: int
    communities: Mapping[str, int]
    node_metrics: pd.DataFrame
    summary: Mapping[str, Any]
    backbone: BackboneReport
    cooccurrence: Cooccurrence

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def label_of(self, entity_id: str) -> str:
        """Label tampilan; jatuh ke id bila entitas tidak ada di katalog."""
        if entity_id in self.entities.index:
            label = self.entities.at[entity_id, "label"]
            if isinstance(label, str) and label.strip():
                return label
        return entity_id

    def type_of(self, entity_id: str) -> Optional[str]:
        if entity_id in self.entities.index:
            value = self.entities.at[entity_id, "entity_type"]
            if isinstance(value, str):
                return value
        return None

    def provenance(self) -> Dict[str, Any]:
        """Asal setiap angka, supaya laporan bisa diaudit tanpa membaca kode."""
        return {
            "population": {
                "total_articles": self.total_articles,
                "entities": len(self.entity_ids),
                "cooccurrence_pairs": self.cooccurrence.pair_count,
                "dropped_mentions": self.cooccurrence.unknown_mentions,
                "source": "bundle.articles / bundle.mentions",
            },
            "association": {
                "method": "npmi_bouma2009",
                "denominator": "seluruh artikel bertanggal di bundle",
                "presence": "biner per (article_id, entity_id)",
            },
            "backbone": self.backbone.as_dict(),
            "metrics": {
                "betweenness": metrics.BETWEENNESS_METHOD,
                "constraint": metrics.CONSTRAINT_METHOD,
                "effective_size": metrics.EFFECTIVE_SIZE_METHOD,
                "pagerank": metrics.PAGERANK_METHOD,
                "closeness": metrics.CLOSENESS_METHOD,
                "community": metrics.COMMUNITY_METHOD,
            },
            "layers": {
                "transmission": {
                    "status": self.layers.get("transmission", "awaiting_input"),
                    "method": None if self.transmission is None else self.transmission.method,
                    "edges": 0 if self.transmission is None else self.transmission.n_edges,
                },
                "sentiment": {
                    "status": self.layers.get("sentiment", "awaiting_input"),
                    "method": None if self.sentiment is None else self.sentiment.method,
                    "entities": 0 if self.sentiment is None else self.sentiment.n_entities,
                },
            },
        }


def build_network(
    bundle: DataBundle,
    config: BackboneConfig = BackboneConfig(),
) -> NetworkBundle:
    """Bangun jaringan dari `mentions` dan hitung seluruh metrik simpul."""
    cooc = cooccurrence(bundle)
    selected, rescued, report = select_edges(cooc, config)

    graph = nx.Graph()
    graph.add_nodes_from(cooc.entity_ids)
    for position, is_rescued in zip(selected, rescued, strict=False):
        u = cooc.entity_ids[int(cooc.pair_u[position])]
        v = cooc.entity_ids[int(cooc.pair_v[position])]
        graph.add_edge(
            u,
            v,
            weight=int(cooc.support[position]),
            npmi=float(cooc.npmi[position]),
            rescued=bool(is_rescued),
        )

    betweenness_map = metrics.betweenness(graph)
    closeness_map = metrics.closeness(graph)
    constraint_map = metrics.constraint(graph)
    effective_map = metrics.effective_size(graph)
    pagerank_map = metrics.pagerank(graph)
    communities = metrics.louvain(graph)

    node_metrics = _node_frame(
        graph,
        cooc,
        communities,
        betweenness=betweenness_map,
        closeness=closeness_map,
        constraint=constraint_map,
        effective_size=effective_map,
        pagerank=pagerank_map,
    )

    return NetworkBundle(
        graph=graph,
        entity_ids=cooc.entity_ids,
        entities=_entity_frame(bundle),
        domain=bundle.domain,
        layers={
            "transmission": bundle.layer_status("transmission"),
            "sentiment": bundle.layer_status("sentiment"),
        },
        transmission=transmission_layer(bundle),
        sentiment=sentiment_layer(bundle),
        total_articles=cooc.total_articles,
        communities=communities,
        node_metrics=node_metrics,
        summary=metrics.summary(graph, communities),
        backbone=report,
        cooccurrence=cooc,
    )


def _entity_frame(bundle: DataBundle) -> pd.DataFrame:
    """Katalog entitas yang dipakai analisis untuk label dan tipe."""
    frame = bundle.entities[["entity_id", "label", "entity_type"]].copy()
    frame["entity_id"] = frame["entity_id"].astype(str)
    return frame.drop_duplicates("entity_id").set_index("entity_id")


def _node_frame(
    graph: nx.Graph,
    cooc: Cooccurrence,
    communities: Mapping[str, int],
    *,
    betweenness: Mapping[str, float],
    closeness: Mapping[str, Optional[float]],
    constraint: Mapping[str, Optional[float]],
    effective_size: Mapping[str, Optional[float]],
    pagerank: Mapping[str, Optional[float]],
) -> pd.DataFrame:
    """Satu baris per entitas; kolom `None` berarti tidak tersedia, bukan nol."""
    rows = []
    for index, entity_id in enumerate(cooc.entity_ids):
        burt = constraint.get(entity_id)
        rows.append(
            {
                "entity_id": entity_id,
                "articles": int(cooc.node_articles[index]),
                "degree": int(graph.degree(entity_id)),
                "pagerank": _round(pagerank.get(entity_id), 5),
                "betweenness": round(float(betweenness.get(entity_id, 0.0)), 6),
                "closeness": _round(closeness.get(entity_id), 4),
                "burt_constraint": _round(burt, 4),
                "effective_size": _round(effective_size.get(entity_id), 2),
                "structural_hole_role": metrics.structural_hole_role(
                    None if burt is None else round(float(burt), 4)
                ),
                "louvain_community": int(communities.get(entity_id, 1)),
            }
        )
    frame = pd.DataFrame(rows)
    return frame.set_index("entity_id")


def _round(value: Optional[float], digits: int) -> Optional[float]:
    return to_number(value, digits)


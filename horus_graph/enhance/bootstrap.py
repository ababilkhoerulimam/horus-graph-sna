"""
Bootstrap artikel untuk selang kepercayaan sentralitas dan stabilitas komunitas.

Satu angka betweenness dari satu korpus tidak punya ketidakpastian yang
dinyatakan. Dengan mengambil ulang artikel (unit sampling yang sebenarnya),
kita bisa melaporkan "betweenness 0,032 dengan selang 90% 0,021-0,044" dan
"komunitas stabil pada ARI 0,86" — bukan dua desimal tanpa dasar.

Resampling dilakukan pada matriks incidensi, bukan pada graf jadi: mengambil
ulang tepi akan merusak struktur derajat dan menghasilkan selang yang terlalu
sempit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import networkx as nx
import numpy as np
import pandas as pd
from scipy import sparse

from ..core import association, metrics
from ..core.backbone import select_edges
from ..core.build import NetworkBundle
from ..core.cooccurrence import Cooccurrence
from . import stats


@dataclass(frozen=True)
class BootstrapResult:
    betweenness: pd.DataFrame
    communities: pd.DataFrame
    ari: Dict[str, Any]
    resamples: int
    seed: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "betweenness": self.betweenness.reset_index().to_dict(orient="records"),
            "communities": self.communities.reset_index().to_dict(orient="records"),
            "ari": self.ari,
            "resamples": self.resamples,
            "seed": self.seed,
            "method": "article_bootstrap",
        }


def bootstrap_network(
    network: NetworkBundle,
    resamples: int = 200,
    seed: int = 42,
    ci: float = 90.0,
) -> BootstrapResult:
    """Resample artikel, bangun ulang backbone, lalu kumpulkan metrik simpul."""
    cooc = network.cooccurrence
    incidence = cooc.incidence
    n_articles = incidence.shape[0]
    if n_articles < 2 or network.graph.number_of_edges() == 0:
        return _empty(resamples, seed)

    config = network.backbone.config()
    rng = np.random.default_rng(seed)
    low = (100.0 - ci) / 2.0
    high = 100.0 - low

    betweenness_draws: List[np.ndarray] = []
    community_draws: List[np.ndarray] = []
    ari_draws: List[float] = []
    baseline_labels = _labels(network, cooc.entity_ids)

    for _ in range(resamples):
        sample = rng.integers(0, n_articles, size=n_articles)
        sampled = _cooccurrence_from(incidence[sample], cooc)
        selected, _, _ = select_edges(sampled, config)
        graph = _graph_from(sampled, selected, cooc.entity_ids)

        values = metrics.betweenness(graph)
        betweenness_draws.append(
            np.array([values.get(entity_id, 0.0) for entity_id in cooc.entity_ids])
        )

        partition = metrics.louvain(graph)
        labels = np.array([partition.get(entity_id, 0) for entity_id in cooc.entity_ids])
        community_draws.append(labels)
        ari_draws.append(stats.adjusted_rand_index(baseline_labels.tolist(), labels.tolist()))

    betweenness = np.vstack(betweenness_draws)
    communities = np.vstack(community_draws)

    betweenness_frame = pd.DataFrame(
        {
            "mean": betweenness.mean(axis=0),
            "sd": betweenness.std(axis=0, ddof=1),
            "ci_low": np.percentile(betweenness, low, axis=0),
            "ci_high": np.percentile(betweenness, high, axis=0),
            "baseline": network.node_metrics["betweenness"].to_numpy(dtype=float),
            "stability": (betweenness > 0).mean(axis=0),
        },
        index=pd.Index(cooc.entity_ids, name="entity_id"),
    ).round(6)

    community_frame = pd.DataFrame(
        {
            "baseline": baseline_labels,
            "mode": _mode_labels(communities),
            "consistency": _consistency(communities),
        },
        index=pd.Index(cooc.entity_ids, name="entity_id"),
    )

    return BootstrapResult(
        betweenness=betweenness_frame,
        communities=community_frame,
        ari={
            "mean": round(float(np.mean(ari_draws)), 4),
            "p05": round(float(np.percentile(ari_draws, 5)), 4),
            "p95": round(float(np.percentile(ari_draws, 95)), 4),
        },
        resamples=resamples,
        seed=seed,
    )


def _cooccurrence_from(sample: sparse.csr_matrix, template: Cooccurrence) -> Cooccurrence:
    """Co-occurrence dari sampel artikel; NPMI dihitung ulang dari total baru."""
    node_articles = np.asarray(sample.sum(axis=0)).ravel().astype(np.int64)
    total = max(int(sample.shape[0]), 1)

    pairs = (sample.T @ sample).tocoo()
    upper = pairs.row < pairs.col
    pair_u = pairs.row[upper].astype(np.int64)
    pair_v = pairs.col[upper].astype(np.int64)
    support = np.rint(pairs.data[upper]).astype(np.int64)

    order = np.lexsort((pair_v, pair_u))
    pair_u, pair_v, support = pair_u[order], pair_v[order], support[order]

    values = association.npmi_array(
        support, node_articles[pair_u], node_articles[pair_v], total
    )
    return Cooccurrence(
        entity_ids=template.entity_ids,
        total_articles=total,
        pair_u=pair_u,
        pair_v=pair_v,
        support=support,
        npmi=values,
        node_articles=node_articles,
        incidence=sample,
        unknown_mentions=0,
    )


def _graph_from(sampled: Cooccurrence, selected: np.ndarray, entity_ids) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(entity_ids)
    for position in selected:
        u = entity_ids[int(sampled.pair_u[position])]
        v = entity_ids[int(sampled.pair_v[position])]
        graph.add_edge(
            u,
            v,
            weight=int(sampled.support[position]),
            npmi=float(sampled.npmi[position]),
        )
    return graph


def _labels(network: NetworkBundle, entity_ids) -> np.ndarray:
    return np.array(
        [int(network.communities.get(entity_id, 0)) for entity_id in entity_ids]
    )


def _mode_labels(draws: np.ndarray) -> np.ndarray:
    """Label komunitas yang paling sering muncul untuk tiap simpul."""
    modes = []
    for column in draws.T:
        values, counts = np.unique(column, return_counts=True)
        modes.append(int(values[int(np.argmax(counts))]))
    return np.array(modes)


def _consistency(draws: np.ndarray) -> np.ndarray:
    """Fraksi resample yang setuju dengan label modus simpul itu."""
    result = []
    for column in draws.T:
        values, counts = np.unique(column, return_counts=True)
        result.append(float(counts.max() / counts.sum()))
    return np.array(result).round(4)


def _empty(resamples: int, seed: int) -> BootstrapResult:
    """Tidak ada resample: frame benar-benar kosong, bukan baris berisi NaN."""
    return BootstrapResult(
        betweenness=pd.DataFrame(
            columns=["mean", "sd", "ci_low", "ci_high", "baseline", "stability"]
        ),
        communities=pd.DataFrame(columns=["baseline", "mode", "consistency"]),
        ari={"mean": None, "p05": None, "p95": None},
        resamples=0,
        seed=seed,
    )

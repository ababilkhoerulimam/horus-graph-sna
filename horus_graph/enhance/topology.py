"""
Profil topologi: k-core, inti-pinggiran, asortativitas, dan homofili tipe.

Angka-angka ini menjawab pertanyaan yang tidak dijawab sentralitas: apakah
jaringan punya inti padat, apakah simpul populer cenderung terhubung ke simpul
populer lain, dan apakah entitas sejenis cenderung mengelompok.
"""

from __future__ import annotations

import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import networkx as nx

from ..core.build import NetworkBundle


@dataclass(frozen=True)
class TopologyProfile:
    core_numbers: Dict[str, int]
    max_core: int
    core_nodes: Tuple[str, ...]
    periphery_nodes: Tuple[str, ...]
    degree_assortativity: Optional[float]
    type_assortativity: Optional[float]
    type_mixing: Dict[str, Dict[str, int]]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "max_core": self.max_core,
            "core_size": len(self.core_nodes),
            "periphery_size": len(self.periphery_nodes),
            "core_nodes": list(self.core_nodes),
            "degree_assortativity": self.degree_assortativity,
            "type_assortativity": self.type_assortativity,
            "type_mixing": self.type_mixing,
            "method": "k_core_and_attribute_assortativity",
        }


def topology_profile(network: NetworkBundle) -> TopologyProfile:
    graph = network.graph
    if graph.number_of_nodes() == 0:
        return TopologyProfile({}, 0, (), (), None, None, {})

    core_numbers = nx.core_number(graph)
    max_core = max(core_numbers.values()) if core_numbers else 0
    # Core number 0 berarti simpul tanpa tepi: itu pinggiran, bukan inti.
    core_nodes = (
        tuple(sorted(node for node, value in core_numbers.items() if value == max_core))
        if max_core > 0
        else ()
    )
    periphery_nodes = tuple(sorted(set(core_numbers) - set(core_nodes)))

    labelled = graph.copy()
    for node in labelled.nodes:
        labelled.nodes[node]["entity_type"] = network.type_of(node) or "Unknown"

    return TopologyProfile(
        core_numbers={node: int(value) for node, value in core_numbers.items()},
        max_core=int(max_core),
        core_nodes=core_nodes,
        periphery_nodes=periphery_nodes,
        degree_assortativity=_degree_assortativity(graph),
        type_assortativity=_attribute_assortativity(labelled),
        type_mixing=_mixing(labelled),
    )


def _degree_assortativity(graph: nx.Graph) -> Optional[float]:
    try:
        with _quiet():
            return _finite(nx.degree_assortativity_coefficient(graph))
    except Exception:
        return None


def _attribute_assortativity(graph: nx.Graph) -> Optional[float]:
    try:
        with _quiet():
            return _finite(nx.attribute_assortativity_coefficient(graph, "entity_type"))
    except Exception:
        return None


@contextmanager
def _quiet():
    """Graf tanpa tepi membuat networkx membagi nol; hasilnya tetap None."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        yield


def _finite(value: float) -> Optional[float]:
    number = float(value)
    if number != number:  # NaN muncul pada graf tanpa variasi derajat/tipe
        return None
    return round(number, 4)


def _mixing(graph: nx.Graph) -> Dict[str, Dict[str, int]]:
    """Matriks pencampuran tipe: berapa tepi menghubungkan tipe A ke tipe B."""
    try:
        with _quiet():
            raw = nx.attribute_mixing_dict(graph, "entity_type")
    except Exception:
        return {}
    return {
        str(source): {str(target): int(count) for target, count in targets.items()}
        for source, targets in raw.items()
    }

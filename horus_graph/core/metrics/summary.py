"""Ringkasan makro jaringan: densitas, kohesi, dan keterhubungan."""

from __future__ import annotations

from typing import Any, Dict

import networkx as nx

from .community import COMMUNITY_METHOD, modularity


def density(edge_count: int, node_count: int) -> float:
    """Densitas graf tak berarah, dibulatkan 4 desimal."""
    if node_count < 2:
        return 0.0
    return round((2.0 * edge_count) / (node_count * (node_count - 1)), 4)


def summary(graph: nx.Graph, communities: Dict[str, int]) -> Dict[str, Any]:
    """
    Angka makro yang aman ditampilkan.

    Diameter dan rata-rata jalur dihitung pada komponen terbesar saja, karena
    graf terputus membuat `nx.diameter` melempar `NetworkXError`.
    """
    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()

    sizes: Dict[int, int] = {}
    for index in communities.values():
        sizes[index] = sizes.get(index, 0) + 1

    raw_modularity = modularity(graph, communities)

    try:
        transitivity = round(float(nx.transitivity(graph)), 4) if edge_count else None
    except Exception:
        transitivity = None

    components = list(nx.connected_components(graph)) if node_count else []
    largest = max(components, key=len) if components else set()
    diameter = None
    average_path = None
    if len(largest) >= 2:
        subgraph = graph.subgraph(largest)
        try:
            diameter = int(nx.diameter(subgraph))
            average_path = round(float(nx.average_shortest_path_length(subgraph)), 4)
        except Exception:
            diameter = None
            average_path = None

    return {
        "nodes": node_count,
        "edges": edge_count,
        "density": density(edge_count, node_count),
        "communities": {
            "count": len(sizes),
            "sizes": [int(size) for _, size in sorted(sizes.items())],
            "modularity": None if raw_modularity is None else round(raw_modularity, 4),
            "method": COMMUNITY_METHOD,
        },
        "transitivity": transitivity,
        "diameter": diameter,
        "average_path_length": average_path,
        "components": len(components),
        "isolated": sum(1 for _, degree in graph.degree() if degree == 0),
    }

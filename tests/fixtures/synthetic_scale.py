"""
Graf sintetis berskala besar, deterministik.

Dipakai untuk mengukur renderer: 10.000 simpul / 50.000 sisi adalah angka
yang disebut kriteria terima V2.1, jadi angkanya harus bisa dibuat ulang
kapan saja tanpa bergantung pada bundle nyata.

Bentuknya meniru yang dikirim API: simpul punya id/label/entity_type/degree,
sisi punya source/target/weight/npmi. Derajat dihitung dari sisinya sendiri,
bukan dikarang, karena renderer memakai derajat untuk ukuran simpul.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List


def synthetic_graph(nodes: int = 10_000, edges: int = 50_000, seed: int = 7) -> Dict[str, Any]:
    """
    Graf dengan derajat yang tidak rata, dibuat dengan benih tetap.

    Rancangan: setiap simpul diberi satu sisi ke simpul berikutnya (cincin,
    menjamin graf terhubung), lalu sisanya diundi dengan peluang yang
    memihak simpul berindeks rendah — sehingga derajatnya berekor panjang
    seperti jaringan nyata, bukan seragam.
    """
    if nodes < 3:
        raise ValueError("Graf skala butuh minimal tiga simpul.")
    if edges < nodes - 1:
        raise ValueError("Sisi tidak cukup untuk menghubungkan semua simpul.")

    rng = random.Random(seed)
    pairs: List[tuple] = []
    seen = set()

    for index in range(nodes):
        pair = (index, (index + 1) % nodes)
        seen.add(pair)
        pairs.append(pair)

    # Peluang memihak indeks rendah: kandidat diambil dari seperlima pertama.
    hot = max(2, nodes // 5)
    while len(pairs) < edges:
        source = rng.randrange(hot)
        target = rng.randrange(nodes)
        if source == target:
            continue
        pair = (min(source, target), max(source, target))
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)

    degree = [0] * nodes
    for source, target in pairs:
        degree[source] += 1
        degree[target] += 1

    node_rows = [
        {
            "id": f"n{index}",
            "label": f"Simpul {index}",
            "entity_type": "Organization" if index % 7 == 0 else "Person",
            "degree": degree[index],
        }
        for index in range(nodes)
    ]
    edge_rows = [
        {
            "source": f"n{source}",
            "target": f"n{target}",
            "weight": rng.randint(1, 40),
            "npmi": round(rng.uniform(0.05, 0.9), 3),
        }
        for source, target in pairs
    ]
    return {"nodes": node_rows, "edges": edge_rows}

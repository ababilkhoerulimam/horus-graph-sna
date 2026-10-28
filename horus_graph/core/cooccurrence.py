"""
Co-occurrence dari tabel `mentions`.

Satu artikel dianggap "menyebut" entitas bila ada minimal satu baris mention,
berapa pun `count`-nya. Keputusan ini penting: kalau `count` dipakai sebagai
bobot, artikel yang menyebut satu nama sepuluh kali akan menggelembungkan
peluang bersama dan NPMI-nya naik tanpa asosiasi yang lebih nyata.

Implementasi memakai matriks incidensi sparse (artikel x entitas) sehingga
biayanya O(mention) + O(pasangan yang benar-benar muncul), bukan O(n_artikel x
n_entitas). Untuk korpus 200 ribu artikel dengan ribuan entitas, bentuk padat
tidak akan muat.

Satu jalur pembentukan pasangan: `from_incidence`. Korpus penuh, sampel
bootstrap, dan null model semuanya lewat situ, supaya NPMI hanya punya satu
definisi dan field baru tidak perlu ditambahkan di tiga tempat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd
from scipy import sparse

from ..io.bundle import DataBundle
from . import association
from .dedup import article_groups


@dataclass(frozen=True)
class Cooccurrence:
    """Pasangan entitas yang muncul bersama, dalam indeks entitas."""

    entity_ids: Tuple[str, ...]
    total_articles: int
    pair_u: np.ndarray
    pair_v: np.ndarray
    support: np.ndarray
    npmi: np.ndarray
    node_articles: np.ndarray
    incidence: sparse.csr_matrix
    unknown_mentions: int = 0
    # Matriks yang dipakai menghitung pasangan. Berbeda dari `incidence` hanya
    # saat dedup aktif: insidensi artikel tetap dipakai untuk tahun dukungan,
    # sementara pasangan dihitung per grup sindikasi.
    pair_incidence: Optional[sparse.csr_matrix] = None
    # Artikel mentah sebelum dedup; `total_articles` adalah penyebut NPMI.
    articles_raw: int = 0

    @property
    def pair_count(self) -> int:
        return int(self.support.size)

    @property
    def counting_matrix(self) -> sparse.csr_matrix:
        return self.incidence if self.pair_incidence is None else self.pair_incidence

    @property
    def group_count(self) -> int:
        return int(self.counting_matrix.shape[0])


def _index_of(index: pd.Index, values: pd.Series) -> np.ndarray:
    """Posisi integer untuk setiap nilai; -1 bila tidak ada di index."""
    return index.get_indexer(values)



def from_incidence(
    incidence: sparse.csr_matrix,
    entity_ids: Tuple[str, ...],
    *,
    total: Optional[int] = None,
    unknown_mentions: int = 0,
    pair_incidence: Optional[sparse.csr_matrix] = None,
    articles_raw: Optional[int] = None,
) -> Cooccurrence:
    """
    Pasangan dari matriks insidensi (artikel x entitas).

    `pair_incidence` diisi hanya saat pasangan harus dihitung per grup
    sindikasi; `incidence` tetap insidensi artikel supaya tahun dukungan tidak
    ikut bergeser.
    """
    matrix = incidence if pair_incidence is None else pair_incidence
    node_articles = np.asarray(matrix.sum(axis=0)).ravel().astype(np.int64)
    denominator = max(int(matrix.shape[0]), 1) if total is None else max(int(total), 1)

    # B.T @ B menghitung pasangan; hanya segitiga atas yang dipakai.
    pairs = (matrix.T @ matrix).tocoo()
    upper = pairs.row < pairs.col
    pair_u = pairs.row[upper].astype(np.int64)
    pair_v = pairs.col[upper].astype(np.int64)
    support = np.rint(pairs.data[upper]).astype(np.int64)

    order = np.lexsort((pair_v, pair_u))
    pair_u, pair_v, support = pair_u[order], pair_v[order], support[order]

    values = association.npmi_array(
        support, node_articles[pair_u], node_articles[pair_v], denominator
    )

    return Cooccurrence(
        entity_ids=entity_ids,
        total_articles=denominator,
        pair_u=pair_u,
        pair_v=pair_v,
        support=support,
        npmi=values,
        node_articles=node_articles,
        incidence=incidence,
        unknown_mentions=unknown_mentions,
        pair_incidence=pair_incidence,
        articles_raw=int(incidence.shape[0]) if articles_raw is None else int(articles_raw),
    )


def graph_from_cooccurrence(
    cooc: Cooccurrence,
    selected: np.ndarray,
    rescued: Optional[np.ndarray] = None,
) -> nx.Graph:
    """
    Graf dari posisi pasangan terpilih.

    `rescued` hanya diisi jalur build. Bootstrap tidak menyelamatkan simpul
    yatim, jadi atributnya tidak boleh muncul di sana sebagai `False` — pembaca
    akan mengira ada keputusan yang diambil.
    """
    graph = nx.Graph()
    graph.add_nodes_from(cooc.entity_ids)
    for order, position in enumerate(selected):
        u = cooc.entity_ids[int(cooc.pair_u[position])]
        v = cooc.entity_ids[int(cooc.pair_v[position])]
        attributes = {
            "weight": int(cooc.support[position]),
            "npmi": float(cooc.npmi[position]),
        }
        if rescued is not None:
            attributes["rescued"] = bool(rescued[order])
        graph.add_edge(u, v, **attributes)
    return graph


def cooccurrence(bundle: DataBundle) -> Cooccurrence:
    """Hitung pasangan co-occurrence seluruh korpus dalam satu pass."""
    entity_ids = tuple(str(value) for value in bundle.entities["entity_id"].tolist())
    if not entity_ids:
        raise ValueError("bundle.entities kosong: tidak ada simpul untuk dihitung")

    entity_index = pd.Index(entity_ids)
    article_index = pd.Index(bundle.articles["article_id"].astype(str))

    mentions = bundle.mentions
    rows = _index_of(article_index, mentions["article_id"].astype(str))
    cols = _index_of(entity_index, mentions["entity_id"].astype(str))
    keep = (rows >= 0) & (cols >= 0)
    unknown = int((~keep).sum())

    # Kehadiran biner: duplikat (artikel, entitas) dijumlahkan lalu dijadikan 1.
    incidence = sparse.coo_matrix(
        (np.ones(int(keep.sum()), dtype=np.float64), (rows[keep], cols[keep])),
        shape=(len(article_index), len(entity_ids)),
    ).tocsr()
    incidence.sum_duplicates()
    incidence.data[:] = 1.0

    groups = article_groups(bundle)
    if groups is None:
        return from_incidence(incidence, entity_ids, unknown_mentions=unknown)

    grouped = sparse.coo_matrix(
        (np.ones(int(keep.sum()), dtype=np.float64), (groups[rows[keep]], cols[keep])),
        shape=(int(groups.max()) + 1, len(entity_ids)),
    ).tocsr()
    grouped.sum_duplicates()
    grouped.data[:] = 1.0

    return from_incidence(
        incidence,
        entity_ids,
        total=int(grouped.shape[0]),
        unknown_mentions=unknown,
        pair_incidence=grouped,
        articles_raw=len(article_index),
    )



def edge_years(
    cooc: Cooccurrence, article_years: np.ndarray, positions: np.ndarray
) -> Dict[int, List[int]]:
    """
    Tahun pendukung untuk pasangan terpilih.

    Dihitung per tahun di dalam jendela, bukan dari agregat global: edge pada
    epos 2024-2026 tidak boleh mengklaim dukungan artikel 2021. Karena itu ia
    memakai `incidence` (artikel), bukan matriks grup.
    """
    if positions.size == 0:
        return {}
    result: Dict[int, List[int]] = {}
    for year in np.unique(article_years):
        rows = np.flatnonzero(article_years == year)
        if rows.size == 0:
            continue
        block = (cooc.incidence[rows].T @ cooc.incidence[rows]).tocsr()
        for position in positions:
            u = int(cooc.pair_u[position])
            v = int(cooc.pair_v[position])
            if block[u, v] > 0:
                result.setdefault(int(position), []).append(int(year))
    return result


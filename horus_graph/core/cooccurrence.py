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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import sparse

from ..io.bundle import DataBundle
from . import association


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

    @property
    def pair_count(self) -> int:
        return int(self.support.size)

    def as_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "source": [self.entity_ids[i] for i in self.pair_u],
                "target": [self.entity_ids[i] for i in self.pair_v],
                "support": self.support.astype(np.int64),
                "npmi": self.npmi,
            }
        )


def _index_of(index: pd.Index, values: pd.Series) -> np.ndarray:
    """Posisi integer untuk setiap nilai; -1 bila tidak ada di index."""
    return index.get_indexer(values)


def cooccurrence(bundle: DataBundle) -> Cooccurrence:
    """Hitung pasangan co-occurrence seluruh korpus dalam satu pass."""
    entity_ids = tuple(str(value) for value in bundle.entities["entity_id"].tolist())
    if not entity_ids:
        raise ValueError("bundle.entities kosong: tidak ada simpul untuk dihitung")

    n_entities = len(entity_ids)
    n_articles = len(bundle.articles)
    total = max(n_articles, 1)

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
        shape=(n_articles, n_entities),
    ).tocsr()
    incidence.sum_duplicates()
    incidence.data[:] = 1.0

    node_articles = np.asarray(incidence.sum(axis=0)).ravel().astype(np.int64)

    # B.T @ B menghitung pasangan; hanya segitiga atas yang dipakai.
    pairs = (incidence.T @ incidence).tocoo()
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
        entity_ids=entity_ids,
        total_articles=total,
        pair_u=pair_u,
        pair_v=pair_v,
        support=support,
        npmi=values,
        node_articles=node_articles,
        incidence=incidence,
        unknown_mentions=unknown,
    )


def edge_years(
    cooc: Cooccurrence, article_years: np.ndarray, positions: np.ndarray
) -> Dict[int, List[int]]:
    """
    Tahun pendukung untuk pasangan terpilih.

    Dihitung per tahun di dalam jendela, bukan dari agregat global: edge pada
    epos 2024-2026 tidak boleh mengklaim dukungan artikel 2021.
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

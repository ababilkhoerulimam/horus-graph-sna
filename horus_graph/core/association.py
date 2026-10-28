"""
Ukuran asosiasi pasangan entitas.

Semua fungsi di sini bekerja pada array numpy supaya satu pass bisa menilai
ratusan ribu pasangan tanpa loop Python. Definisi NPMI mengikuti Bouma (2009):
nilai ternormalisasi di [-1, 1], dengan `-log(p_uv)` sebagai penyebut sehingga
pasangan yang sangat jarang tidak otomatis mendapat skor tinggi.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

import numpy as np

# Ambang minimum agar `log` tidak meledak; bukan nilai substantif.
_EPS = 1e-12


def npmi(
    support: int,
    node_u: int,
    node_v: int,
    total: int,
) -> Optional[float]:
    """NPMI satu pasangan; `None` bila tidak terdefinisi (bukan 0.0 karangan)."""
    if support <= 0 or total <= 0 or node_u <= 0 or node_v <= 0:
        return None
    p_uv = support / total
    if p_uv >= 1.0:
        return None
    denom = -math.log(p_uv)
    if denom <= 0:
        return None
    value = math.log(p_uv / ((node_u / total) * (node_v / total))) / denom
    return max(-1.0, min(1.0, value))


def npmi_array(
    support: np.ndarray,
    node_u: np.ndarray,
    node_v: np.ndarray,
    total: int,
) -> np.ndarray:
    """Versi vektor dari :func:`npmi`; entri tak terdefinisi menjadi `nan`."""
    support = np.asarray(support, dtype=np.float64)
    node_u = np.asarray(node_u, dtype=np.float64)
    node_v = np.asarray(node_v, dtype=np.float64)
    if total <= 0 or support.size == 0:
        return np.full(support.shape, np.nan)

    with np.errstate(divide="ignore", invalid="ignore"):
        p_uv = support / float(total)
        p_u = node_u / float(total)
        p_v = node_v / float(total)
        denom = -np.log(np.maximum(p_uv, _EPS))
        value = np.log((p_uv + _EPS) / np.maximum(p_u * p_v, _EPS)) / denom

    value[~np.isfinite(value)] = np.nan
    value[p_uv >= 1.0] = np.nan
    return np.clip(value, -1.0, 1.0)


def jaccard(support: int, node_u: int, node_v: int) -> float:
    union = node_u + node_v - support
    if union <= 0:
        return 0.0
    return max(0.0, min(1.0, support / union))


def salton(support: int, node_u: int, node_v: int) -> float:
    denom = math.sqrt(max(1, node_u) * max(1, node_v))
    return max(0.0, min(1.0, support / denom))


def hypergeometric_p(support: int, total: int, cu: int, cv: int) -> float:
    """p-value uji hipergeometrik (Tumminello et al. 2011) untuk satu pasangan."""
    if support <= 0 or cu <= 0 or cv <= 0 or total <= 0:
        return 1.0
    n = int(max(100, total))
    k1 = min(cu, cv)
    k2 = max(cu, cv)
    support = min(support, k1)
    try:
        from scipy.stats import hypergeom

        value = float(hypergeom.sf(support - 1, n, k1, k2))
    except Exception:
        expected = (k1 * k2) / n
        if support <= expected:
            return 1.0
        variance = (k1 * k2 * (n - k1) * (n - k2)) / (n * n * (n - 1))
        std_dev = math.sqrt(max(1e-9, variance))
        z = (support - 0.5 - expected) / std_dev
        value = 0.5 * math.erfc(z / math.sqrt(2.0))
    return max(0.0, min(1.0, value))


def benjamini_hochberg(p_values: Sequence[float]) -> List[float]:
    """
    q-value Benjamini-Hochberg, urutan keluaran mengikuti urutan masukan.

    Tanpa koreksi ini, menguji ratusan pasangan sekaligus membuat sebagian edge
    lolos "signifikan" semata karena jumlah uji, bukan karena asosiasi nyata.
    """
    count = len(p_values)
    if count == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    q_values = [1.0] * count
    running = 1.0
    for rank in range(count, 0, -1):
        position, p_value = indexed[rank - 1]
        candidate = min(1.0, float(p_value) * count / rank)
        running = min(running, candidate)
        q_values[position] = running
    return q_values


def hypergeometric_p_array(
    support: np.ndarray, cu: np.ndarray, cv: np.ndarray, total: int
) -> np.ndarray:
    """
    Versi vektor dari `hypergeometric_p`.

    Konvensi `n = max(100, total)` dipertahankan persis; tanpa itu vektor dan
    skalar bisa memberi p yang berbeda untuk pasangan yang sama, dan pembaca
    tidak punya cara tahu mana yang dipakai.
    """
    support = np.asarray(support, dtype=np.int64)
    cu = np.asarray(cu, dtype=np.int64)
    cv = np.asarray(cv, dtype=np.int64)
    n = int(max(100, total))
    k1 = np.minimum(cu, cv)
    k2 = np.maximum(cu, cv)
    values = np.ones(support.shape, dtype=np.float64)
    valid = (support > 0) & (k1 > 0) & (k2 > 0) & (total > 0)
    if not np.any(valid):
        return values

    from scipy.stats import hypergeom

    clipped = np.minimum(support[valid], k1[valid])
    values[valid] = hypergeom.sf(clipped - 1, n, k1[valid], k2[valid])
    return np.clip(values, 0.0, 1.0)


"""
Graf sintetis untuk pengukuran skala.

Angka kriteria terima V2.1 hanya berarti kalau grafnya bisa dibuat ulang persis.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

from synthetic_scale import synthetic_graph  # noqa: E402


def test_jumlah_simpul_dan_sisi_tepat() -> None:
    graph = synthetic_graph(500, 2000)

    assert len(graph["nodes"]) == 500
    assert len(graph["edges"]) == 2000
    assert {node["id"] for node in graph["nodes"]} >= {"n0", "n499"}


def test_benih_yang_sama_memberi_graf_yang_sama() -> None:
    assert synthetic_graph(200, 800, seed=3) == synthetic_graph(200, 800, seed=3)


def test_benih_berbeda_memberi_sisi_berbeda() -> None:
    pertama = synthetic_graph(200, 800, seed=3)
    kedua = synthetic_graph(200, 800, seed=4)

    assert pertama["edges"] != kedua["edges"]


def test_derajat_dihitung_dari_sisi() -> None:
    graph = synthetic_graph(50, 200)
    derajat = {node["id"]: node["degree"] for node in graph["nodes"]}
    hitung = {f"n{index}": 0 for index in range(50)}
    for edge in graph["edges"]:
        hitung[edge["source"]] += 1
        hitung[edge["target"]] += 1

    assert derajat == hitung


def test_permintaan_yang_tidak_masuk_akal_ditolak() -> None:
    with pytest.raises(ValueError):
        synthetic_graph(2, 5)
    with pytest.raises(ValueError):
        synthetic_graph(100, 50)

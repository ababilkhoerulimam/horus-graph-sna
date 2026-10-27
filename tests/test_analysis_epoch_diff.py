"""
Diff epos: siapa naik, siapa turun, sisi mana yang lahir dan mati.

Dua jebakan yang dijaga di sini:

1. Label komunitas Louvain tidak stabil antar jalankan. "Komunitas 2 menjadi 3"
   sering hanya berarti algoritma memulai dari titik lain, bukan perpindahan.
   Perbandingan harus lewat pemetaan tumpang tindih, dan ringkasannya ARI.
2. Simpul yang hanya ada di satu epos bukan "delta nol". Ia `entered`/`exited`
   dengan delta `None`, karena tidak ada dua pengukuran untuk dikurangkan.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from horus_graph.api.queries import _community_mapping, _edge_diff, compare_epochs
from horus_graph.core.temporal import build_temporal


def _frame(mapping: dict) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "entity_id": list(mapping),
            "degree": [1] * len(mapping),
            "betweenness": [0.5] * len(mapping),
            "burt_constraint": [0.25] * len(mapping),
            "louvain_community": list(mapping.values()),
        }
    )
    return frame.set_index("entity_id")


def test_label_komunitas_yang_bertukar_nomor_bukan_perpindahan() -> None:
    base = _frame({"A": 1, "B": 1, "C": 2})
    targ = _frame({"A": 2, "B": 2, "C": 1})

    mapping, agreement = _community_mapping(base, targ, ["A", "B", "C"])

    assert mapping == {1: 2, 2: 1}
    assert agreement == 1.0


def test_komunitas_yang_benar_benar_berpisah_menurunkan_kesepakatan() -> None:
    base = _frame({"A": 1, "B": 1, "C": 1, "D": 1})
    targ = _frame({"A": 1, "B": 1, "C": 2, "D": 2})

    _mapping, agreement = _community_mapping(base, targ, ["A", "B", "C", "D"])

    assert agreement is not None and agreement < 1.0


def test_tanpa_simpul_bertahan_tidak_ada_kesepakatan() -> None:
    base = _frame({"A": 1})
    targ = _frame({"B": 1})

    mapping, agreement = _community_mapping(base, targ, [])

    assert mapping == {}
    assert agreement is None


def _slice(edges: list) -> SimpleNamespace:
    return SimpleNamespace(
        edges=pd.DataFrame(edges, columns=["source", "target", "support", "npmi"])
    )


def test_sisi_lahir_dan_mati_dihitung_dari_pasangan() -> None:
    before = _slice([("A", "B", 5, 0.3), ("B", "C", 4, 0.2)])
    after = _slice([("B", "C", 9, 0.4), ("C", "D", 2, 0.1)])

    gained, lost = _edge_diff(before, after, limit=10)

    assert [(row["source"], row["target"]) for row in gained] == [("C", "D")]
    assert [(row["source"], row["target"]) for row in lost] == [("A", "B")]
    # Support yang dilaporkan milik epos tempat sisi itu hidup.
    assert gained[0]["support"] == 2
    assert lost[0]["support"] == 5


def test_arah_sisi_tidak_membuat_pasangan_ganda() -> None:
    before = _slice([("A", "B", 5, 0.3)])
    after = _slice([("B", "A", 5, 0.3)])

    gained, lost = _edge_diff(before, after, limit=10)

    assert gained == [] and lost == []


def test_batas_jumlah_sisi_dihormati() -> None:
    before = _slice([("A", f"N{index}", index, 0.1) for index in range(20)])
    after = _slice([])

    _gained, lost = _edge_diff(before, after, limit=10)

    assert len(lost) == 10


# --- ujung ke ujung -------------------------------------------------------


def _two_epochs(bundle_factory, left_entities, right_entities):
    """
    Dua epos dengan artikel latar.

    Tanpa artikel tanpa entitas, setiap pasangan muncul di *seluruh* artikel
    eposnya, sehingga NPMI menjadi 0/0 dan seluruh sisi gugur di ambang mana pun.
    """
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in left_entities]
    rows += [(f"art{i:03d}", e, 1) for i in range(16, 24) for e in right_entities]
    dates = ["2021-06-01"] * 8 + ["2021-07-01"] * 8
    dates += ["2023-06-01"] * 8 + ["2023-07-01"] * 8
    return bundle_factory(
        sorted(set(left_entities) | set(right_entities)),
        rows,
        articles=32,
        ego=left_entities[0],
        dates=dates,
        epochs=[("e1", 2021, 2022), ("e2", 2023, 2024)],
    )


def test_simpul_baru_tidak_punya_delta(bundle_factory) -> None:
    bundle = _two_epochs(bundle_factory, ("A", "B"), ("C", "D"))
    temporal = build_temporal(bundle)

    result = compare_epochs(temporal.by_id("e1"), temporal.by_id("e2"))

    assert result["persisted_count"] == 0
    assert set(result["nodes_gained"]) == {"C", "D"}
    assert set(result["nodes_lost"]) == {"A", "B"}
    for row in result["nodes"]:
        assert row["status"] in {"entered", "exited"}
        assert row["delta_betweenness"] is None
        assert row["delta_degree"] is None
        assert row["community_shifted"] is None


def test_dua_epos_beririsan_memberi_delta_dan_peta_komunitas(bundle_factory) -> None:
    bundle = _two_epochs(bundle_factory, ("A", "B", "C"), ("B", "C", "D"))
    temporal = build_temporal(bundle)

    result = compare_epochs(temporal.by_id("e1"), temporal.by_id("e2"))

    assert result["persisted_count"] == 2
    assert result["community_map"], "peta komunitas tidak boleh kosong bila ada irisan"
    assert 0.0 <= result["community_agreement"] <= 1.0
    # Epos kedua memuat sisi baru, jadi hitungannya tidak boleh nol.
    assert result["edges_gained_count"] >= 1

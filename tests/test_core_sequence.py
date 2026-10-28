"""
Urutan sentralitas lintas jendela, pada graf yang peringkatnya bisa dihitung tangan.

Yang dijaga:

1. Peringkat dibandingkan di dalam jendelanya sendiri, dan simpul yang tidak ada
   di sebuah jendela mendapat null — bukan 0, bukan peringkat terakhir.
2. Agregat all-time tidak ikut sebagai jendela: ia gabungan, dan memasukkannya
   akan membuat setiap simpul terlihat "bertahan" di satu jendela yang bukan
   jendela.
3. Korelasi peringkat tidak dilaporkan saat dasarnya terlalu tipis; angka dari
   dua simpul bersama akan terbaca sebagai temuan.
"""

from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from horus_graph.core import sequence
from horus_graph.core.temporal import EpochSlice, EpochWindow, TemporalBundle


def _slice(epoch_id: str, rows: dict, start: int = 2020) -> EpochSlice:
    frame = pd.DataFrame(
        [
            {"entity_id": node, "degree": degree, "betweenness": betweenness}
            for node, (degree, betweenness) in rows.items()
        ]
    ).set_index("entity_id")
    return EpochSlice(
        window=EpochWindow(epoch_id, epoch_id, start, start),
        graph=nx.Graph(),
        node_metrics=frame,
        edges=pd.DataFrame(),
        density=0.0,
        articles=0,
        isolated=(),
        top_broker=None,
        top_autonomy=None,
    )


def _temporal(*slices: EpochSlice) -> TemporalBundle:
    return TemporalBundle(slices=tuple(slices), total_articles=0, year_span=(2020, 2024))


def test_peringkat_berganti_menghasilkan_gerak_berlawanan() -> None:
    temporal = _temporal(
        _slice("e1", {"A": (1, 0.5), "B": (2, 0.9)}),
        _slice("e2", {"A": (2, 0.9), "B": (1, 0.1)}),
    )

    hasil = sequence.build_sequence(temporal)
    per_node = {row["id"]: row for row in hasil["series"]}

    assert hasil["status"] == "ready"
    assert hasil["windows"] == ["e1", "e2"]
    # Peringkat 1 = tertinggi; A naik dari 2 ke 1, B turun dari 1 ke 2.
    assert per_node["A"]["betweenness_rank"] == [2, 1]
    assert per_node["A"]["betweenness_rank_shift"] == 1
    assert per_node["B"]["betweenness_rank_shift"] == -1


def test_gerak_diurutkan_menurut_besar_perubahan() -> None:
    temporal = _temporal(
        _slice("e1", {"A": (1, 0.1), "B": (2, 0.2), "C": (3, 0.9)}),
        _slice("e2", {"A": (3, 0.9), "B": (2, 0.2), "C": (1, 0.1)}),
    )

    hasil = sequence.build_sequence(temporal)

    assert [row["id"] for row in hasil["movers"]] == ["A", "C"]
    assert hasil["movers"][0]["betweenness_rank_shift"] == 2


def test_simpul_yang_hilang_mendapat_null_bukan_nol() -> None:
    temporal = _temporal(
        _slice("e1", {"A": (1, 0.5), "B": (2, 0.9)}),
        _slice("e2", {"B": (2, 0.9)}),
    )

    hasil = sequence.build_sequence(temporal)
    a = next(row for row in hasil["series"] if row["id"] == "A")

    assert a["degree_rank"][1] is None
    assert a["degree"][1] is None
    assert a["betweenness_rank"][1] is None
    # Tanpa ujung akhir, tidak ada arah yang bisa diklaim.
    assert a["betweenness_rank_shift"] is None
    assert a["windows_present"] == 1


def test_all_time_bukan_jendela() -> None:
    temporal = _temporal(
        _slice("e1", {"A": (1, 0.5), "B": (2, 0.9)}),
        _slice("e2", {"A": (2, 0.9), "B": (1, 0.5)}),
        _slice("all_time", {"A": (2, 0.9), "B": (2, 0.5)}),
    )

    hasil = sequence.build_sequence(temporal)

    assert hasil["windows"] == ["e1", "e2"]


def test_seri_dipecah_oleh_id_saat_nilai_sama() -> None:
    temporal = _temporal(
        _slice("e1", {"B": (1, 0.5), "A": (1, 0.5)}),
        _slice("e2", {"B": (1, 0.5), "A": (1, 0.5)}),
    )

    hasil = sequence.build_sequence(temporal)
    per_node = {row["id"]: row for row in hasil["series"]}

    assert per_node["A"]["betweenness_rank"][0] == 1
    assert per_node["B"]["betweenness_rank"][0] == 2


def test_tanpa_epos_menunggu_masukan() -> None:
    hasil = sequence.build_sequence(_temporal())

    assert hasil["status"] == "awaiting_input"
    assert "jendela epos" in hasil["reason"]
    assert hasil["series"] == []


def test_satu_jendela_belum_cukup() -> None:
    hasil = sequence.build_sequence(_temporal(_slice("e1", {"A": (1, 0.5)})))

    assert hasil["status"] == "awaiting_input"
    assert "minimal 2" in hasil["reason"]


def test_korelasi_peringkat_satu_untuk_urutan_yang_sama() -> None:
    temporal = _temporal(
        _slice("e1", {"A": (3, 0.9), "B": (2, 0.5), "C": (1, 0.1)}),
        _slice("e2", {"A": (3, 0.8), "B": (2, 0.4), "C": (1, 0.2)}),
    )

    hasil = sequence.build_sequence(temporal)

    assert hasil["rank_agreement"][0]["shared_nodes"] == 3
    assert hasil["rank_agreement"][0]["spearman"] == pytest.approx(1.0)


def test_korelasi_tidak_dilaporkan_untuk_dua_simpul() -> None:
    temporal = _temporal(
        _slice("e1", {"A": (2, 0.9), "B": (1, 0.1)}),
        _slice("e2", {"A": (2, 0.8), "B": (1, 0.2)}),
    )

    hasil = sequence.build_sequence(temporal)

    assert hasil["rank_agreement"][0]["spearman"] is None

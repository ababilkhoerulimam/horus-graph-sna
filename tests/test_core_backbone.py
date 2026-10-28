"""Seleksi backbone: ambang, penyelamatan konektivitas, dan jejak auditnya."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from horus_graph.core import cooccurrence
from horus_graph.core.backbone import BackboneConfig, select_edges
from horus_graph.core.build import build_network


def _edges(cooc, selected):
    return {
        frozenset((cooc.entity_ids[int(cooc.pair_u[p])], cooc.entity_ids[int(cooc.pair_v[p])]))
        for p in selected
    }


def test_ambang_support_dan_npmi_memilih_pasangan_kuat(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(6) for e in ("A", "B")]
    rows += [(f"art{i:03d}", "A", 1) for i in range(6, 10)]
    bundle = bundle_factory(["A", "B"], rows, articles=20)
    cooc = cooccurrence(bundle)

    selected, rescued, report = select_edges(cooc, BackboneConfig(min_support=3, min_npmi=0.2))
    assert len(selected) == 1
    assert not rescued.any()
    assert report.candidate_pairs == 1
    assert report.above_threshold == 1
    assert report.added_for_support == 0


def test_pasangan_di_bawah_support_tidak_lolos_tapi_diselamatkan(bundle_factory):
    # A-B kuat; C hanya sekali bersama A -> support 1, wajib diselamatkan.
    rows = [(f"art{i:03d}", e, 1) for i in range(5) for e in ("A", "B")]
    rows += [("art005", "A", 1), ("art005", "C", 1)]
    bundle = bundle_factory(["A", "B", "C"], rows, articles=30)
    cooc = cooccurrence(bundle)

    selected, rescued, report = select_edges(cooc, BackboneConfig(min_support=3, min_npmi=0.2))
    assert _edges(cooc, selected) == {frozenset(("A", "B")), frozenset(("A", "C"))}
    assert report.added_for_support == 1
    assert report.entities_below_threshold == ("C",)
    assert report.still_isolated == ()
    assert int(rescued.sum()) == 1


def test_penyelamatan_bisa_dimatikan(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(5) for e in ("A", "B")]
    rows += [("art005", "A", 1), ("art005", "C", 1)]
    bundle = bundle_factory(["A", "B", "C"], rows, articles=30)
    cooc = cooccurrence(bundle)

    selected, _, report = select_edges(
        cooc, BackboneConfig(min_support=3, min_npmi=0.2, rescue_isolated=False)
    )
    assert _edges(cooc, selected) == {frozenset(("A", "B"))}
    assert report.still_isolated == ("C",)


def test_entitas_tanpa_mention_tetap_dilaporkan_terisolasi(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(5) for e in ("A", "B")]
    bundle = bundle_factory(["A", "B", "HANTU"], rows, articles=10)
    cooc = cooccurrence(bundle)

    _, _, report = select_edges(cooc, BackboneConfig())
    assert report.still_isolated == ("HANTU",)
    assert "HANTU" in report.entities_below_threshold


def test_edge_diselamatkan_ditandai_setelah_pengurutan(bundle_factory):
    # Dua entitas yatim dengan support berbeda: mask harus mengikuti urutan akhir.
    rows = [(f"art{i:03d}", e, 1) for i in range(6) for e in ("A", "B")]
    rows += [("art010", "A", 1), ("art010", "C", 1)]
    rows += [("art011", "A", 1), ("art011", "D", 1)]
    bundle = bundle_factory(["A", "B", "C", "D"], rows, articles=40)
    cooc = cooccurrence(bundle)

    selected, rescued, report = select_edges(cooc, BackboneConfig(min_support=3, min_npmi=0.2))
    flags = {
        frozenset((cooc.entity_ids[int(cooc.pair_u[p])], cooc.entity_ids[int(cooc.pair_v[p])])): bool(r)
        for p, r in zip(selected, rescued, strict=False)
    }
    assert flags[frozenset(("A", "B"))] is False
    assert flags[frozenset(("A", "C"))] is True
    assert flags[frozenset(("A", "D"))] is True
    assert report.added_for_support == 2


def test_konfigurasi_tidak_valid_ditolak():
    with pytest.raises(ValueError):
        BackboneConfig(min_support=0)
    with pytest.raises(ValueError):
        BackboneConfig(min_npmi=1.5)


def test_tanpa_pasangan_menghasilkan_graf_kosong_tapi_laporan_lengkap(bundle_factory):
    bundle = bundle_factory(["A", "B"], [("art000", "A", 1), ("art001", "B", 1)], articles=5)
    cooc = cooccurrence(bundle)
    selected, rescued, report = select_edges(cooc, BackboneConfig())
    assert selected.size == 0
    assert not rescued.any()
    assert report.candidate_pairs == 0
    assert report.still_isolated == ("A", "B")
    assert np.isfinite(cooc.npmi).sum() == 0


# --- gerbang q ------------------------------------------------------------


def _mixed_significance(bundle_factory):
    """
    Satu pasangan benar-benar berasosiasi, satu pasangan hanya kebetulan.

    A-B: 30 dari 100 artikel, padahal margin keduanya 50 — persis yang
    diharapkan kebetulan. A-C/A-D/C-D: seluruh artikel C dan D memuat A,
    sehingga mustahil terjadi secara acak.
    """
    rows = [(f"art{i:03d}", "A", 1) for i in range(0, 50)]
    rows += [(f"art{i:03d}", "B", 1) for i in range(20, 70)]
    rows += [(f"art{i:03d}", e, 1) for i in range(0, 10) for e in ("C", "D")]
    return bundle_factory(["A", "B", "C", "D"], rows, articles=100)


def _selected_names(cooc, selected) -> set:
    return {
        frozenset((cooc.entity_ids[int(cooc.pair_u[p])], cooc.entity_ids[int(cooc.pair_v[p])]))
        for p in selected
    }


def test_tanpa_min_q_semua_pasangan_lolos_ambang_dipakai(bundle_factory):
    cooc = cooccurrence(_mixed_significance(bundle_factory))

    selected, _, report = select_edges(cooc, BackboneConfig(min_support=3, min_npmi=0.1))

    assert len(selected) == 4
    # Uji tetap dijalankan (keluarga 4 pasangan), tetapi tidak ada yang
    # dibuang: significant_pairs 0 berarti "tidak ada gerbang", bukan "gagal".
    assert report.min_q is None
    assert report.tested_pairs == 4
    assert report.significant_pairs == 0


def test_gerbang_q_membuang_pasangan_kuat_tapi_tidak_signifikan(bundle_factory):
    cooc = cooccurrence(_mixed_significance(bundle_factory))

    selected, _, report = select_edges(
        cooc, BackboneConfig(min_support=3, min_npmi=0.1, min_q=0.01)
    )

    names = _selected_names(cooc, selected)
    assert frozenset(("A", "B")) not in names
    assert names == {
        frozenset(("A", "C")),
        frozenset(("A", "D")),
        frozenset(("C", "D")),
    }
    # Keluarga uji adalah seluruh pasangan teramati, bukan hanya yang lolos.
    assert report.tested_pairs == 4
    assert report.significant_pairs == 3


def test_gerbang_q_menolak_cooccurrence_tanpa_q(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(6) for e in ("A", "B")]
    cooc = cooccurrence(bundle_factory(["A", "B"], rows, articles=10))
    stripped = replace(cooc, q_value=None)

    with pytest.raises(ValueError):
        select_edges(stripped, BackboneConfig(min_q=0.05))


def test_edge_membawa_q_saat_gerbang_aktif(bundle_factory):
    bundle = _mixed_significance(bundle_factory)

    network = build_network(bundle, BackboneConfig(min_support=3, min_npmi=0.1, min_q=0.01))

    assert network.graph.number_of_edges() == 3
    for _, _, data in network.graph.edges(data=True):
        assert 0.0 <= data["q"] <= 0.01


def test_tanpa_gerbang_q_memilih_pasangan_yang_sama(bundle_factory):
    """Kehadiran q_value tidak boleh mengubah seleksi saat gerbangnya mati."""
    cooc = cooccurrence(_mixed_significance(bundle_factory))
    config = BackboneConfig(min_support=3, min_npmi=0.1)

    with_q = select_edges(cooc, config)
    without_q = select_edges(replace(cooc, q_value=None), config)

    assert np.array_equal(with_q[0], without_q[0])
    assert np.array_equal(with_q[1], without_q[1])

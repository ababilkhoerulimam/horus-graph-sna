"""Co-occurrence dari `mentions`: kehadiran biner, denominator, dan NPMI."""

from __future__ import annotations

import math

import numpy as np
import pytest

from horus_graph.core import association, cooccurrence


def _pair(cooc, u: str, v: str):
    i = cooc.entity_ids.index(u)
    j = cooc.entity_ids.index(v)
    low, high = min(i, j), max(i, j)
    mask = (cooc.pair_u == low) & (cooc.pair_v == high)
    if not mask.any():
        return None
    return int(cooc.support[mask][0]), float(cooc.npmi[mask][0])


def test_kehadiran_biner_tidak_digandakan_count(bundle_factory):
    # `count` tinggi di satu artikel tetap satu kejadian, bukan tiga.
    bundle = bundle_factory(
        ["A", "B"],
        [("art000", "A", 5), ("art000", "B", 1), ("art001", "A", 1)],
        articles=4,
    )
    cooc = cooccurrence(bundle)
    support, _ = _pair(cooc, "A", "B")
    assert support == 1
    assert int(cooc.node_articles[cooc.entity_ids.index("A")]) == 2


def test_duplikat_baris_mention_dijumlahkan_sekali(bundle_factory):
    bundle = bundle_factory(
        ["A", "B"],
        [("art000", "A", 1), ("art000", "A", 1), ("art000", "B", 1)],
        articles=3,
    )
    cooc = cooccurrence(bundle)
    assert int(cooc.node_articles[cooc.entity_ids.index("A")]) == 1
    assert _pair(cooc, "A", "B")[0] == 1


def test_denominator_memakai_seluruh_artikel(bundle_factory):
    # 1 dari 10 artikel -> p_uv = 0.1, bukan 1.0 (yang membuat NPMI tak terdefinisi).
    bundle = bundle_factory(["A", "B"], [("art000", "A", 1), ("art000", "B", 1)], articles=10)
    cooc = cooccurrence(bundle)
    assert cooc.total_articles == 10
    support, value = _pair(cooc, "A", "B")
    expected = math.log((1 / 10) / (0.1 * 0.1)) / -math.log(1 / 10)
    assert value == pytest.approx(expected, abs=1e-9)


def test_npmi_positif_untuk_pasangan_yang_selalu_bersama(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(4) for e in ("A", "B")]
    bundle = bundle_factory(["A", "B"], rows, articles=20)
    cooc = cooccurrence(bundle)
    _, value = _pair(cooc, "A", "B")
    assert value > 0.2
    assert -1.0 <= value <= 1.0


def test_npmi_negatif_untuk_pasangan_yang_saling_menghindar(bundle_factory):
    rows = [(f"art{i:03d}", "A", 1) for i in range(5)]
    rows += [(f"art{i:03d}", "B", 1) for i in range(5, 10)]
    bundle = bundle_factory(["A", "B"], rows, articles=10)
    cooc = cooccurrence(bundle)
    assert _pair(cooc, "A", "B") is None  # tidak pernah bersama
    # p_uv = 1 -> -log(p_uv) = 0 -> tidak terdefinisi, bukan nilai ekstrem.
    assert association.npmi(10, 10, 10, 10) is None
    # Dua entitas yang muncul di semua artikel tapi hanya sekali bersama: -1.
    assert association.npmi(1, 10, 10, 10) == pytest.approx(-1.0)


def test_pasangan_hanya_segitiga_atas_dan_unik(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(3) for e in ("A", "B", "C")]
    bundle = bundle_factory(["A", "B", "C"], rows, articles=5)
    cooc = cooccurrence(bundle)
    assert cooc.pair_count == 3
    assert np.all(cooc.pair_u < cooc.pair_v)
    keys = list(zip(cooc.pair_u.tolist(), cooc.pair_v.tolist()))
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


def test_entitas_tanpa_artikel_tetap_simpul_dengan_nol(bundle_factory):
    bundle = bundle_factory(["A", "B", "Z"], [("art000", "A", 1), ("art000", "B", 1)], articles=2)
    cooc = cooccurrence(bundle)
    assert cooc.entity_ids == ("A", "B", "Z")
    assert int(cooc.node_articles[2]) == 0


def test_mention_untuk_entitas_tak_dikenal_dibuang_dan_dihitung(bundle_factory):
    bundle = bundle_factory(
        ["A", "B"],
        [("art000", "A", 1), ("art000", "B", 1), ("art000", "GHOST", 1)],
        articles=2,
    )
    cooc = cooccurrence(bundle)
    assert cooc.unknown_mentions == 1
    assert cooc.pair_count == 1


def test_artikel_di_luar_tabel_articles_tidak_menambah_pasangan(bundle_factory):
    bundle = bundle_factory(
        ["A", "B"],
        [("art000", "A", 1), ("art999", "B", 1), ("art000", "B", 1)],
        articles=2,
    )
    cooc = cooccurrence(bundle)
    assert cooc.unknown_mentions == 1
    assert _pair(cooc, "A", "B")[0] == 1


def test_entity_ids_kosong_ditolak(bundle_factory):
    bundle = bundle_factory([], [], articles=1)
    with pytest.raises(ValueError):
        cooccurrence(bundle)

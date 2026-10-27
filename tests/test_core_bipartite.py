"""Bipartit topik-aktor: pengecualian media, NPMI, dan keanggotaan topik."""

from __future__ import annotations

import pytest

from horus_graph.core.bipartite import build_bipartite


def _corpus(bundle_factory):
    # 10 artikel topik T1 (A + media), 10 artikel topik T2 (A di 5, B di 10).
    rows = [(f"art{i:03d}", "A", 1) for i in range(0, 15)]
    rows += [(f"art{i:03d}", "B", 1) for i in range(10, 20)]
    rows += [(f"art{i:03d}", "MEDIA", 1) for i in range(0, 20)]
    article_topics = [(f"art{i:03d}", "T1") for i in range(0, 10)]
    article_topics += [(f"art{i:03d}", "T2") for i in range(10, 20)]
    return bundle_factory(
        ["A", "B", "MEDIA"],
        rows,
        articles=20,
        entity_types=["Person", "Person", "Source"],
        topics=["T1", "T2"],
        article_topics=article_topics,
        sources=["MEDIA"] * 20,
    )


def test_media_dikecualikan_dari_sisi_aktor(bundle_factory):
    result = build_bipartite(_corpus(bundle_factory))
    assert set(result.actors["entity_id"]) == {"A", "B"}
    assert "MEDIA" not in set(result.edges["entity_id"])


def test_media_tetap_dihitung_untuk_lapisan_sankey(bundle_factory):
    result = build_bipartite(_corpus(bundle_factory))
    media = result.media_topics.set_index(["source_id", "topic_id"])["articles"]
    assert media[("MEDIA", "T1")] == 10
    assert media[("MEDIA", "T2")] == 10


def test_support_dan_npmi_dihitung_dari_artikel_bersama(bundle_factory):
    result = build_bipartite(_corpus(bundle_factory), min_support=1)
    edges = result.edges.set_index(["topic_id", "entity_id"])

    assert edges.at[("T1", "A"), "support"] == 10
    assert edges.at[("T2", "A"), "support"] == 5
    assert edges.at[("T2", "B"), "support"] == 10

    # p_ta = 5/20, p_t = 10/20, p_a = 15/20 -> asosiasi negatif.
    assert edges.at[("T2", "A"), "npmi"] < 0
    assert edges.at[("T2", "B"), "npmi"] > 0


def test_ambang_min_support_membuang_edge_tipis(bundle_factory):
    result = build_bipartite(_corpus(bundle_factory), min_support=6)
    assert ("T2", "A") not in set(zip(result.edges["topic_id"], result.edges["entity_id"]))


def test_keanggotaan_topik_diurutkan_menurut_npmi_bukan_volume(bundle_factory):
    result = build_bipartite(_corpus(bundle_factory), min_support=1, membership_top_n=1)
    # Di T2, B lebih khas daripada A meski A muncul di lebih banyak topik.
    assert result.membership["T2"] == ("B",)


def test_keanggotaan_menghormati_batas_min_npmi(bundle_factory):
    result = build_bipartite(
        _corpus(bundle_factory), min_support=1, membership_min_npmi=0.5
    )
    assert result.membership.get("T2", ()) == ("B",)
    assert "A" not in result.membership.get("T1", ())


def test_ringkasan_menghitung_edge_negatif(bundle_factory):
    result = build_bipartite(_corpus(bundle_factory), min_support=1)
    summary = result.summary()
    assert summary["topics"] == 2
    assert summary["actors"] == 2
    assert summary["edges"] == 3
    assert summary["negative_edges"] == 1


def test_bundle_tanpa_topik_menghasilkan_edge_kosong(bundle_factory):
    bundle = bundle_factory(["A"], [("art000", "A", 1)], articles=1)
    result = build_bipartite(bundle)
    assert result.edges.empty
    assert result.membership == {}
    assert result.actors["entity_id"].tolist() == ["A"]

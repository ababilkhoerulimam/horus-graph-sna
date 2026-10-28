"""
Dedup sindikasi dan satu jalur pembentukan pasangan.

Yang dijaga: satu rilis yang dimuat banyak portal dihitung satu kali, bundle
tanpa kolom `dedupe_group` menghasilkan angka yang sama persis dengan sebelum
fitur ini ada, dan pembentukan pasangan hanya punya satu definisi.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from horus_graph.core.backbone import select_edges
from horus_graph.core.build import build_network
from horus_graph.core.cooccurrence import cooccurrence, from_incidence, graph_from_cooccurrence


def _bundle(bundle_factory):
    # Dua entitas yang selalu muncul bersama di empat artikel.
    rows = [(f"art{i:03d}", entity, 1) for i in range(4) for entity in ("A", "B")]
    return bundle_factory(["A", "B"], rows, articles=4, ego="A")


def test_tiga_artikel_satu_grup_dihitung_sekali(bundle_factory):
    # Tiga salinan menyebut A dan B; artikel keempat hanya menyebut A.
    rows = [(f"art{i:03d}", entity, 1) for i in range(3) for entity in ("A", "B")]
    rows.append(("art003", "A", 1))
    bundle = bundle_factory(["A", "B"], rows, articles=4, ego="A")
    articles = bundle.articles.assign(dedupe_group=["g1", "g1", "g1", None])

    cooc = cooccurrence(replace(bundle, articles=articles))

    # g1 (tiga salinan) + satu artikel tunggal = dua unit dukungan.
    assert cooc.total_articles == 2
    assert int(cooc.support[0]) == 1
    assert cooc.articles_raw == 4


def test_tanpa_kolom_dedupe_group_tidak_berubah(bundle_factory):
    bundle = _bundle(bundle_factory)
    kosong = bundle.articles.assign(dedupe_group=None)

    tanpa = cooccurrence(bundle)
    dengan = cooccurrence(replace(bundle, articles=kosong))

    assert tanpa.total_articles == 4
    assert dengan.total_articles == 4
    assert np.array_equal(tanpa.support, dengan.support)
    assert np.allclose(tanpa.npmi, dengan.npmi, equal_nan=True)


def test_from_incidence_setara_dengan_cooccurrence(bundle_factory):
    cooc = cooccurrence(_bundle(bundle_factory))

    ulang = from_incidence(cooc.incidence, cooc.entity_ids)

    assert np.array_equal(cooc.pair_u, ulang.pair_u)
    assert np.array_equal(cooc.pair_v, ulang.pair_v)
    assert np.array_equal(cooc.support, ulang.support)
    assert np.allclose(cooc.npmi, ulang.npmi, equal_nan=True)
    assert ulang.total_articles == cooc.total_articles


def test_graph_from_cooccurrence_setara_dengan_build_network(bundle_factory):
    bundle = _bundle(bundle_factory)
    network = build_network(bundle)
    selected, rescued, _ = select_edges(network.cooccurrence, network.backbone.config())

    graph = graph_from_cooccurrence(network.cooccurrence, selected, rescued)

    assert set(graph.edges) == set(network.graph.edges)
    for u, v in graph.edges:
        assert graph.edges[u, v]["weight"] == network.graph.edges[u, v]["weight"]
        assert graph.edges[u, v]["rescued"] == network.graph.edges[u, v]["rescued"]


def test_alias_dibawa_ke_network(bundle_factory):
    bundle = _bundle(bundle_factory)
    entities = bundle.entities.assign(aliases=[["EMV", "Egy M"], None])

    network = build_network(replace(bundle, entities=entities))

    assert network.aliases["A"] == ("EMV", "Egy M")
    assert "B" not in network.aliases


def test_artikel_mentah_dilaporkan_terpisah(bundle_factory):
    bundle = _bundle(bundle_factory)
    articles = bundle.articles.assign(dedupe_group=["g1", "g1", None, None])

    network = build_network(replace(bundle, articles=articles))

    assert network.corpus_articles == 4
    assert network.total_articles == 3


"""Profil topologi: k-core, asortativitas, dan homofili tipe."""

from __future__ import annotations

from horus_graph.core import build_network
from horus_graph.enhance.topology import topology_profile


def _network(bundle_factory):
    # Inti: A-B-C saling terhubung; D dan E hanya menempel ke A.
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 6) for e in ("A", "B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(6, 9) for e in ("A", "D")]
    rows += [(f"art{i:03d}", e, 1) for i in range(9, 12) for e in ("A", "E")]
    return build_network(
        bundle_factory(
            ["A", "B", "C", "D", "E"],
            rows,
            articles=40,
            entity_types=["Organization", "Person", "Person", "Location", "Location"],
        )
    )


def test_k_core_memisahkan_inti_dan_pinggiran(bundle_factory):
    profile = topology_profile(_network(bundle_factory))
    assert profile.max_core == 2
    assert profile.core_nodes == ("A", "B", "C")
    assert set(profile.periphery_nodes) == {"D", "E"}


def test_asortativitas_derajat_dilaporkan(bundle_factory):
    profile = topology_profile(_network(bundle_factory))
    assert profile.degree_assortativity is not None
    assert -1.0 <= profile.degree_assortativity <= 1.0


def test_homofili_tipe_dan_matriks_pencampuran(bundle_factory):
    profile = topology_profile(_network(bundle_factory))
    assert profile.type_assortativity is not None
    assert set(profile.type_mixing) == {"Organization", "Person", "Location"}
    assert profile.type_mixing["Person"]["Person"] >= 2


def test_dict_hasil_memuat_metode(bundle_factory):
    payload = topology_profile(_network(bundle_factory)).as_dict()
    assert payload["method"] == "k_core_and_attribute_assortativity"
    assert payload["core_size"] == 3
    assert payload["max_core"] == 2


def test_graf_kosong_aman(bundle_factory):
    bundle = bundle_factory(["A"], [("art000", "A", 1)], articles=2)
    profile = topology_profile(build_network(bundle))
    assert profile.max_core == 0
    assert profile.core_nodes == ()
    assert profile.degree_assortativity is None

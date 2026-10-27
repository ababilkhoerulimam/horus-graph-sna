"""Resolusi nama entitas: urutan pencarian harus deterministik."""

from __future__ import annotations

from horus_graph.analysis import resolve_entity
from horus_graph.core import build_network


def _network(bundle_factory):
    bundle = bundle_factory(
        ["Egy Maulana Vikri", "Liga 1", "Persib Bandung"],
        [
            ("art000", "Egy Maulana Vikri", 1),
            ("art000", "Liga 1", 1),
            ("art001", "Persib Bandung", 1),
        ],
        articles=3,
    )
    return build_network(bundle)


def test_id_persis_menang(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "Liga 1") == "Liga 1"


def test_case_insensitive(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "liga 1") == "Liga 1"
    assert resolve_entity(network, "EGY MAULANA VIKRI") == "Egy Maulana Vikri"


def test_substring_mencocokkan_id(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "egy") == "Egy Maulana Vikri"
    assert resolve_entity(network, "persib") == "Persib Bandung"


def test_query_kosong_dan_tidak_dikenal_mengembalikan_none(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "") is None
    assert resolve_entity(network, "   ") is None
    assert resolve_entity(network, "entitas-yang-tidak-ada") is None


def test_spasi_di_tepi_diabaikan(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "  Liga 1  ") == "Liga 1"

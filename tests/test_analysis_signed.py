"""D6: keluaran bertanda hanya status dan alasan, tanpa satu pun angka."""

from __future__ import annotations

from horus_graph.analysis import signed_edges
from horus_graph.core import build_network


def _assert_no_numbers(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert not isinstance(key, (int, float)), f"kunci angka: {key!r}"
            _assert_no_numbers(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_numbers(item)
    else:
        assert not isinstance(value, (int, float)), f"nilai angka: {value!r}"


def _network(bundle_factory, sentiment=None):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 4) for e in ("A", "B")]
    return build_network(bundle_factory(["A", "B"], rows, articles=6, sentiment=sentiment))


def test_keluaran_tanpa_satu_pun_angka(bundle_factory):
    payload = signed_edges(_network(bundle_factory))

    assert payload["status"] == "not_published"
    assert payload["reason"]
    _assert_no_numbers(payload)


def test_status_sentimen_per_entitas_dilaporkan(bundle_factory):
    without = signed_edges(_network(bundle_factory))
    assert without["entity_sentiment"] == "awaiting_input"
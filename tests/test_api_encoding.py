"""
Skala ukuran: peringkat, bukan konstanta milik satu dataset.

Yang dijaga di sini bukan estetika, melainkan satu janji: dataset baru dengan
distribusi berbeda tetap mendapat gambar yang terisi penuh. Konstanta lama
(`(deg-11)/(47-11)`) akan menaruh seluruh simpul di kelas bawah pada graf kecil,
tanpa satu pun error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from horus_graph.api.encoding import TIERS, encode
from horus_graph.api.serializers import node_payloads
from horus_graph.api.state import AppState
from horus_graph.core.anomaly import detect_anomalies
from horus_graph.core.bipartite import build_bipartite
from horus_graph.core.build import build_network
from horus_graph.core.temporal import build_temporal
from horus_graph.presentation import resolve_presentation


def _metrics(**rows):
    return {
        name: {
            "degree": values[0],
            "articles": values[1],
            "betweenness": values[2],
            "effective_size": values[3],
        }
        for name, values in rows.items()
    }


def test_peringkat_naik_bersama_degree() -> None:
    block = encode(
        _metrics(
            kecil=(1, 10, 0.0, 1.0),
            sedang=(5, 20, 0.01, 3.0),
            besar=(20, 40, 0.05, 9.0),
        )
    )

    assert block["besar"]["rank_degree"] > block["sedang"]["rank_degree"]
    assert block["sedang"]["rank_degree"] > block["kecil"]["rank_degree"]
    assert block["besar"]["size_rank"] > block["kecil"]["size_rank"]


@pytest.mark.parametrize("jumlah", [5, 6, 17, 77, 400])
def test_kelima_tier_selalu_terisi(jumlah: int) -> None:
    """Berapa pun ukuran grafnya, kelima kelas ukuran harus terpakai."""
    rows = {
        f"ent_{index:03d}": (index, index * 10, index / 100.0, float(index))
        for index in range(jumlah)
    }

    block = encode(_metrics(**rows))
    tiers = {item["radius_tier"] for item in block.values()}

    assert tiers == set(range(1, TIERS + 1))


def test_seri_diputus_oleh_id_sehingga_stabil() -> None:
    """Tanpa pemutus seri, dua simpul identik bisa bertukar tier antar proses."""
    rows = {name: (3, 10, 0.01, 2.0) for name in ("zulu", "alpha", "mike")}

    pertama = encode(_metrics(**rows))
    kedua = encode(_metrics(**dict(reversed(list(rows.items())))))

    assert pertama == kedua
    assert [name for name, _ in sorted(pertama.items(), key=lambda kv: kv[1]["label_priority"])] == [
        "alpha",
        "mike",
        "zulu",
    ]


def test_metrik_kosong_ditaruh_di_belakang_bukan_dianggap_nol() -> None:
    block = encode(
        _metrics(
            terukur=(10, 50, 0.02, 4.0),
            kosong=(None, None, None, None),
        )
    )

    assert block["terukur"]["label_priority"] < block["kosong"]["label_priority"]
    assert block["kosong"]["rank_degree"] == 0.0


def test_satu_simpul_tetap_punya_skala() -> None:
    block = encode(_metrics(tunggal=(1, 1, 0.0, 1.0)))

    assert block["tunggal"]["size_rank"] == 1.0
    assert block["tunggal"]["radius_tier"] == 1


def test_graf_kosong_tidak_melempar() -> None:
    assert encode({}) == {}


def test_payload_simpul_membawa_blok_ukuran(bundle_factory) -> None:
    """Jalur HTTP yang sebenarnya: setiap simpul wajib punya kelima field."""
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 12) for e in ("A", "B", "C", "D", "E")]
    bundle = bundle_factory(["A", "B", "C", "D", "E"], rows, articles=20, ego="A")
    state = AppState(
        root=Path("."),
        bundle=bundle,
        presentation=resolve_presentation(bundle),
        network=build_network(bundle),
        temporal=build_temporal(bundle),
        bipartite=build_bipartite(bundle),
        anomaly=detect_anomalies(bundle),
        build_seconds=0.0,
    )

    nodes = node_payloads(state)

    assert len(nodes) == 5
    for node in nodes:
        assert 1 <= node["radius_tier"] <= TIERS
        assert 0.0 <= node["size_rank"] <= 1.0
        assert node["label_priority"] >= 1
    assert {node["radius_tier"] for node in nodes} == set(range(1, TIERS + 1))

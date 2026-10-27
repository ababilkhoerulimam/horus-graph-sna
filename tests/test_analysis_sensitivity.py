"""
Ambang backbone sebagai data, dan kurva sensitivitasnya.

Dua hal yang dijaga: ambang milik bundle dipakai saat membangun jaringan (tanpa
menyunting kode atau flag server), dan kurva sensitivitas menunjukkan berapa
sisi yang bertahan bila ambangnya digeser.
"""

from __future__ import annotations

import argparse
import json

import pytest

from horus_graph.analysis.sensitivity import sensitivity
from horus_graph.contract.models import BackboneSettings
from horus_graph.core.backbone import BackboneConfig
from horus_graph.core.build import backbone_config, build_network


def _corpus(bundle_factory):
    rows = []
    for index in range(0, 12):
        rows.append((f"art{index:03d}", "A", 1))
        rows.append((f"art{index:03d}", "B", 1))
    for index in range(0, 4):
        rows.append((f"art{index:03d}", "C", 1))
    return bundle_factory(["A", "B", "C"], rows, articles=20, ego="A")


def test_ambang_dari_manifest_dipakai(bundle_factory) -> None:
    bundle = _corpus(bundle_factory)
    bundle.manifest.backbone = BackboneSettings(min_support=2, min_npmi=0.1)

    assert backbone_config(bundle).min_support == 2
    assert build_network(bundle).backbone.min_support == 2


def test_konfigurasi_eksplisit_menang(bundle_factory) -> None:
    bundle = _corpus(bundle_factory)
    bundle.manifest.backbone = BackboneSettings(min_support=2)

    network = build_network(bundle, BackboneConfig(min_support=7))

    assert network.backbone.min_support == 7


def test_tanpa_blok_memakai_default(bundle_factory) -> None:
    bundle = _corpus(bundle_factory)

    config = backbone_config(bundle)

    assert (config.min_support, config.min_npmi) == (3, 0.2)


def test_kurva_support_tidak_naik_saat_ambang_naik(bundle_factory) -> None:
    bundle = _corpus(bundle_factory)

    result = sensitivity(bundle, points=6)

    passed = [point["passed"] for point in result["by_support"]]
    assert result["status"] == "ready"
    assert result["candidate_pairs"] > 0
    assert passed == sorted(passed, reverse=True)


def test_jumlah_sisi_adalah_lolos_tambah_penyelamat(bundle_factory) -> None:
    """`edges` boleh naik-turun; `passed` tidak, dan jumlah keduanya harus cocok."""
    bundle = _corpus(bundle_factory)

    result = sensitivity(bundle, points=6)

    for point in result["by_support"]:
        assert point["edges"] == point["passed"] + point["rescued"]


def test_kurva_npmi_tidak_naik_saat_ambang_naik(bundle_factory) -> None:
    bundle = _corpus(bundle_factory)

    result = sensitivity(bundle, points=6)

    passed = [point["passed"] for point in result["by_npmi"]]
    assert passed == sorted(passed, reverse=True)
    # Grid dimulai dari nilai NPMI terendah yang benar-benar ada pada data,
    # bukan dari 0 yang belum tentu ada pasangannya.
    assert result["by_npmi"][0]["min_npmi"] <= result["active"]["min_npmi"]


def test_titik_aktif_ada_di_kurva_support(bundle_factory) -> None:
    bundle = _corpus(bundle_factory)
    bundle.manifest.backbone = BackboneSettings(min_support=4)

    result = sensitivity(bundle, points=6)

    supports = [point["min_support"] for point in result["by_support"]]
    assert result["active"]["min_support"] == 4
    assert 4 in supports


def test_jumlah_titik_menentukan_panjang_kurva(bundle_factory) -> None:
    """
    `points` adalah batas atas, bukan janji: grid tidak bisa lebih panjang dari
    jumlah nilai berbeda yang ada pada data, dan nilai aktif menambah paling
    banyak satu titik.
    """
    bundle = _corpus(bundle_factory)

    for requested in (4, 9):
        for key in ("by_support", "by_npmi"):
            length = len(sensitivity(bundle, points=requested)[key])
            assert 2 <= length <= requested + 1


def test_nilai_aktif_selalu_ada_di_kedua_kurva(bundle_factory) -> None:
    bundle = _corpus(bundle_factory)
    bundle.manifest.backbone = BackboneSettings(min_support=4, min_npmi=0.35)

    result = sensitivity(bundle, points=6)

    assert result["active"]["min_support"] in [p["min_support"] for p in result["by_support"]]
    assert result["active"]["min_npmi"] in [p["min_npmi"] for p in result["by_npmi"]]


def test_simpul_terisolasi_dihitung_dari_yang_tersentuh(bundle_factory) -> None:
    bundle = _corpus(bundle_factory)

    result = sensitivity(bundle, points=4)

    for point in result["by_support"]:
        assert point["nodes"] + point["isolated"] == 3
        assert point["rescued"] <= point["edges"]


@pytest.mark.parametrize("nilai", [0, -1])
def test_min_support_tidak_sah_ditolak(nilai: int) -> None:
    with pytest.raises(ValueError):
        BackboneConfig(min_support=nilai)


def test_grid_menjangkau_support_tertinggi_di_data() -> None:
    """
    Regresi: batas atas tetap (20) membuat kurva support pada bundle nyata
    seluruhnya datar, karena support di sana mencapai ribuan. Grid harus
    mencapai nilai maksimum yang ada, sehingga titik keruntuhan terlihat.
    """
    from horus_graph.analysis.sensitivity import _grid

    values = [1, 2, 3, 500, 9039]

    grid = _grid(values, 12, 3, integral=True)

    assert grid[0] == 1
    assert grid[-1] == 9039
    assert grid == sorted(grid)
    assert len(set(grid)) == len(grid)


def test_kurva_bundle_nyata_tidak_datar(golden_bundle) -> None:
    """Pada korpus sebenarnya, menggeser ambang harus benar-benar mengubah graf."""
    result = sensitivity(golden_bundle, points=12)

    edges = [point["edges"] for point in result["by_support"]]
    assert result["candidate_pairs"] > 0
    assert max(edges) > min(edges), "kurva support datar: grid tidak menjangkau data"
    # Titik terakhir menandai ambang di mana hampir semua sisi gugur.
    assert edges[-1] < edges[0]


def _build_args(**overrides) -> argparse.Namespace:
    values = {"bundle": "ignored", "min_support": None, "min_npmi": None,
              "top": 0, "all": False, "json": True}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_cli_build_memakai_ambang_bundle(bundle_factory, monkeypatch, capsys) -> None:
    """
    Regresi: default argparse dulu selalu 3/0.2, sehingga `manifest.backbone`
    tidak pernah berpengaruh lewat CLI meski engine sudah membacanya.
    """
    from horus_graph import cli

    bundle = _corpus(bundle_factory)
    bundle.manifest.backbone = BackboneSettings(min_support=2, min_npmi=0.1)
    monkeypatch.setattr(cli, "load_bundle", lambda _path: bundle)

    assert cli._cmd_build(_build_args()) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["backbone"]["min_support"] == 2
    assert report["backbone"]["min_npmi"] == 0.1


def test_cli_build_flag_eksplisit_menang(bundle_factory, monkeypatch, capsys) -> None:
    from horus_graph import cli

    bundle = _corpus(bundle_factory)
    bundle.manifest.backbone = BackboneSettings(min_support=2, min_npmi=0.1)
    monkeypatch.setattr(cli, "load_bundle", lambda _path: bundle)

    assert cli._cmd_build(_build_args(min_support=5, min_npmi=0.4)) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["backbone"]["min_support"] == 5
    assert report["backbone"]["min_npmi"] == 0.4

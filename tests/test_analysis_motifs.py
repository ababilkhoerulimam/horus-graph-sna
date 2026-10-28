"""
Rich-club sebagai artefak: dihitung di luar server, dibaca saat bundle dimuat.

Yang dijaga: artefak rusak atau belum ada tidak boleh tampil sebagai angka.
Karena kurva mentah naik secara konstruksi, tidak ada jalur yang mengirim
rich-club tanpa pembanding acak.
"""

from __future__ import annotations

import json

from horus_graph.analysis import motifs as motif_artifact
from horus_graph.core.build import build_network


def _network(bundle_factory):
    """
    Segitiga A-B-C plus D menempel di C.

    Ketiga pasangan segitiga muncul di artikel berbeda supaya marginalnya
    tidak sama dengan kebersamaannya — tanpa itu NPMI-nya nol dan tidak ada
    sisi yang lolos ambang.
    """
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 16) for e in ("B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(16, 24) for e in ("A", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(24, 30) for e in ("C", "D")]
    return bundle_factory(["A", "B", "C", "D"], rows, articles=70)


def test_compute_mengisi_sensus_triad_dan_rich_club(bundle_factory):
    network = build_network(_network(bundle_factory))

    payload = motif_artifact.compute(network, motif_artifact.MotifParams(replicates=2))

    assert payload["motifs"]["triads"]["status"] == "ready"
    assert payload["motifs"]["triads"]["triangles"] >= 1
    # Empat simpul: tidak ada ambang derajat yang menyisakan 10 simpul.
    assert payload["motifs"]["rich_club"]["status"] == "awaiting_input"
    assert payload["params"]["replicates"] == 2


def test_artefak_ditulis_dan_dibaca_kembali(bundle_factory, tmp_path):
    network = build_network(_network(bundle_factory))
    payload = motif_artifact.compute(network, motif_artifact.MotifParams(replicates=2))

    path = motif_artifact.write_artifact(tmp_path, payload)
    stored = motif_artifact.read_artifact(tmp_path)

    assert path.name == "motifs.json"
    assert stored is not None
    assert stored["motifs"]["triads"]["classes"] == payload["motifs"]["triads"]["classes"]
    # Tulis atomik tidak meninggalkan berkas sementara.
    assert not list(tmp_path.glob("*.tmp"))


def test_artefak_hilang_dibaca_sebagai_none(tmp_path):
    assert motif_artifact.read_artifact(tmp_path) is None


def test_artefak_rusak_dibaca_sebagai_none(tmp_path):
    (tmp_path / "motifs.json").write_text("{bukan json", encoding="utf-8")

    assert motif_artifact.read_artifact(tmp_path) is None


def test_artefak_tanpa_kunci_motifs_diabaikan(tmp_path):
    (tmp_path / "motifs.json").write_text(json.dumps({"lain": 1}), encoding="utf-8")

    assert motif_artifact.read_artifact(tmp_path) is None


def test_parameter_berbeda_dianggap_basi(bundle_factory, tmp_path):
    network = build_network(_network(bundle_factory))
    payload = motif_artifact.compute(network, motif_artifact.MotifParams(replicates=2))
    motif_artifact.write_artifact(tmp_path, payload)
    stored = motif_artifact.read_artifact(tmp_path)
    assert stored is not None

    assert motif_artifact.stale(stored, motif_artifact.MotifParams(replicates=2)) is False
    assert motif_artifact.stale(stored, motif_artifact.MotifParams(replicates=5)) is True
    assert motif_artifact.stale(stored, motif_artifact.MotifParams(seed=7)) is True

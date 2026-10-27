"""Ledakan wacana per entitas (Kleinberg dua keadaan)."""

from __future__ import annotations

import pytest

from horus_graph.enhance.bursts import BurstConfig, detect_bursts, entity_monthly_counts


def _bundle(bundle_factory, monthly: dict[str, int]):
    """Artikel per bulan untuk entitas A; B selalu dua artikel per bulan."""
    dates = []
    rows = []
    for period, count in monthly.items():
        year, month = (int(part) for part in period.split("-"))
        for index in range(count):
            article = f"art{len(dates):03d}"
            dates.append(f"{year:04d}-{month:02d}-15")
            rows.append((article, "A", 1))
            if index < 2:
                rows.append((article, "B", 1))
    return bundle_factory(["A", "B"], rows, articles=len(dates), dates=dates)


def test_ledakan_terdeteksi_pada_rentang_yang_benar(bundle_factory):
    monthly = {f"2023-{month:02d}": 2 for month in range(1, 13)}
    monthly.update({"2023-06": 12, "2023-07": 14, "2023-08": 11})
    report = detect_bursts(_bundle(bundle_factory, monthly))

    bursts = report.bursts[report.bursts["entity_id"] == "A"]
    assert not bursts.empty
    top = bursts.iloc[0]
    assert top["start"] <= "2023-06"
    assert top["end"] >= "2023-08"
    assert top["lift"] > 1.5


def test_entitas_di_bawah_ambang_artikel_dilewati(bundle_factory):
    monthly = {f"2023-{month:02d}": 1 for month in range(1, 13)}
    monthly["2023-06"] = 4
    report = detect_bursts(_bundle(bundle_factory, monthly), BurstConfig(min_articles=20))
    assert report.bursts.empty


def test_deret_datar_tidak_menghasilkan_ledakan(bundle_factory):
    monthly = {f"2023-{month:02d}": 3 for month in range(1, 13)}
    report = detect_bursts(
        _bundle(bundle_factory, monthly), BurstConfig(min_articles=10, gamma=5.0)
    )
    assert report.bursts.empty


def test_rentang_lebih_pendek_dari_min_months_dibuang(bundle_factory):
    monthly = {f"2023-{month:02d}": 2 for month in range(1, 13)}
    monthly["2023-06"] = 20
    report = detect_bursts(
        _bundle(bundle_factory, monthly),
        BurstConfig(min_articles=10, min_months=3, gamma=1.0),
    )
    assert report.bursts.empty


def test_matriks_bulanan_lengkap_termasuk_bulan_kosong(bundle_factory):
    bundle = _bundle(bundle_factory, {"2023-01": 3, "2023-04": 3})
    table = entity_monthly_counts(bundle)
    assert list(table.columns) == ["2023-01", "2023-02", "2023-03", "2023-04"]
    assert table.at["A", "2023-02"] == 0


def test_konfigurasi_tidak_valid_ditolak():
    with pytest.raises(ValueError):
        BurstConfig(burst_ratio=1.0)
    with pytest.raises(ValueError):
        BurstConfig(gamma=-1)


def test_bundle_tanpa_mention_tidak_melempar(bundle_factory):
    bundle = bundle_factory(["A"], [], articles=2)
    report = detect_bursts(bundle)
    assert report.bursts.empty
    assert report.months == ()

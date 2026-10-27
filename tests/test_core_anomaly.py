"""Anomali volume: isi bulan kosong, baseline MAD, dan bulan parsial."""

from __future__ import annotations

import calendar

import pytest

from horus_graph.core.anomaly import AnomalyConfig, detect_anomalies, monthly_counts


def _baseline(year: int = 2023, months: int = 12) -> dict[str, int]:
    """12 bulan dengan variasi cukup agar MAD tidak nol."""
    return {f"{year}-{month:02d}": 8 + (month % 4) for month in range(1, months + 1)}


def _dates(month_counts: dict[str, int]) -> list[str]:
    """Tanggal di akhir bulan, supaya bulan terakhir dianggap tutup penuh."""
    dates = []
    for period, count in month_counts.items():
        year, month = (int(part) for part in period.split("-"))
        last_day = calendar.monthrange(year, month)[1]
        dates.extend([f"{year:04d}-{month:02d}-{last_day:02d}"] * count)
    return dates


def _bundle(bundle_factory, counts: dict[str, int], dates=None):
    dates = dates or _dates(counts)
    return bundle_factory(["A"], [("art000", "A", 1)], articles=len(dates), dates=dates)


def test_bulan_tanpa_artikel_diisi_nol(bundle_factory):
    bundle = bundle_factory(
        ["A"],
        [("art000", "A", 1)],
        articles=3,
        dates=["2024-01-05", "2024-03-05", "2024-03-06"],
    )
    assert monthly_counts(bundle) == {"2024-01": 1, "2024-02": 0, "2024-03": 2}


def test_baseline_kurang_tidak_menghasilkan_spike(bundle_factory):
    counts = {f"2024-{month:02d}": 5 for month in range(1, 5)}
    report = detect_anomalies(_bundle(bundle_factory, counts))

    # Empat bulan belum cukup jadi pembanding: tidak ada yang dinilai, dan
    # tidak ada yang dilaporkan sebagai lonjakan.
    assert report.months == 4
    assert report.spikes == ()


def test_lonjakan_tajam_terdeteksi(bundle_factory):
    counts = _baseline()
    counts["2024-01"] = 200
    counts["2024-02"] = 10
    report = detect_anomalies(_bundle(bundle_factory, counts))

    # Kandidat spike adalah semua bulan dengan z > 0; yang teratas harus lonjakan.
    assert report.spikes[0]["period"] == "2024-01"
    assert report.spikes[0]["severity"] == "KRITIS"
    assert report.spikes[0]["baseline_median"] == 9.5
    assert report.spikes[0]["article_count"] == 200


def test_bulan_parsial_tidak_dilaporkan_sebagai_spike(bundle_factory):
    # Bulan terakhir baru terisi sampai tanggal 3, jadi lonjakannya belum bisa dinilai.
    counts = _baseline()
    counts["2024-01"] = 300
    dates = [d if not d.startswith("2024-01") else "2024-01-03" for d in _dates(counts)]
    dates[0] = "2023-01-01"
    report = detect_anomalies(_bundle(bundle_factory, counts, dates))

    assert report.partial_periods == ("2024-01",)
    assert all(spike["period"] != "2024-01" for spike in report.spikes)


def test_bulan_berurutan_digabung_mengambil_puncaknya(bundle_factory):
    counts = _baseline()
    counts["2024-01"] = 60
    counts["2024-02"] = 120
    report = detect_anomalies(_bundle(bundle_factory, counts))
    periods = [spike["period"] for spike in report.spikes]
    assert periods[0] == "2024-02"
    assert "2024-01" not in periods


def test_dedupe_bisa_dimatikan(bundle_factory):
    counts = _baseline()
    counts["2024-01"] = 60
    counts["2024-02"] = 120
    report = detect_anomalies(
        _bundle(bundle_factory, counts),
        AnomalyConfig(dedupe_consecutive=False, top_n=5),
    )
    assert [spike["period"] for spike in report.spikes][:2] == ["2024-02", "2024-01"]


def test_skala_nol_tidak_membagi_dengan_nol(bundle_factory):
    counts = {f"2023-{month:02d}": 10 for month in range(1, 13)}
    counts["2024-01"] = 40
    report = detect_anomalies(_bundle(bundle_factory, counts))

    # Dua belas bulan identik berarti MAD 0. z tidak terdefinisi, jadi bulan
    # itu dilewati — bukan dibagi nol, bukan dilaporkan sebagai lonjakan.
    assert report.spikes == ()


def test_spike_menyimpan_baseline_yang_dipakai(bundle_factory):
    counts = {f"2023-{month:02d}": 10 + month for month in range(1, 13)}
    counts["2024-01"] = 200
    report = detect_anomalies(_bundle(bundle_factory, counts))

    spike = report.spikes[0]
    assert spike["period"] == "2024-01"
    assert spike["baseline_n"] == 12
    assert spike["window_months"] == 12
    assert spike["baseline_median"] == pytest.approx(16.5)
    assert spike["baseline_mad"] == pytest.approx(3.0)


def test_bundle_tanpa_artikel_tidak_melempar(bundle_factory):
    bundle = bundle_factory(["A"], [], articles=0)
    report = detect_anomalies(bundle)
    assert report.months == 0
    assert report.spikes == ()

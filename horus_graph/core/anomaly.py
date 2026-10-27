"""
Deteksi lonjakan volume wacana per bulan.

Metode: robust z-score terhadap median + MAD jendela bulan-bulan sebelumnya.
Rata-rata dan simpangan baku biasa akan ditarik oleh bulan ekstrem itu sendiri,
sehingga lonjakan paling besar justru paling sulit terdeteksi.
"""

from __future__ import annotations

import calendar
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..io.bundle import DataBundle

DEFAULT_SEVERITY: Dict[str, float] = {"KRITIS": 3.5, "TINGGI": 2.5, "SEDANG": 1.5}


@dataclass(frozen=True)
class AnomalyConfig:
    window_months: int = 12
    min_baseline_months: int = 8
    mad_scale: float = 1.4826
    top_n: int = 3
    severity: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SEVERITY))
    dedupe_consecutive: bool = True


@dataclass(frozen=True)
class AnomalyReport:
    monthly_counts: Dict[str, int]
    series: pd.DataFrame
    spikes: Tuple[Dict[str, Any], ...]
    partial_periods: Tuple[str, ...]
    config: AnomalyConfig

    @property
    def months(self) -> int:
        return len(self.monthly_counts)


def monthly_counts(bundle: DataBundle) -> Dict[str, int]:
    """Artikel per bulan kalender; bulan tanpa artikel diisi 0, bukan dilewati."""
    if bundle.articles.empty:
        return {}
    published = pd.to_datetime(bundle.articles["published_at"], format="ISO8601", utc=True)
    periods = published.dt.strftime("%Y-%m").dropna()
    counts = {str(period): int(value) for period, value in periods.value_counts().items()}
    return _fill_gaps(counts)


def detect_anomalies(
    bundle: DataBundle, config: Optional[AnomalyConfig] = None
) -> AnomalyReport:
    config = config or AnomalyConfig()
    counts = monthly_counts(bundle)
    if not counts:
        return AnomalyReport({}, _empty_series(), (), (), config)

    published = pd.to_datetime(bundle.articles["published_at"], format="ISO8601", utc=True)
    first_date = published.min().date()
    last_date = published.max().date()

    periods = sorted(counts)
    values = [counts[period] for period in periods]
    partial = _partial_periods(periods, first_date, last_date)

    rows: List[Dict[str, Any]] = []
    spikes: List[Dict[str, Any]] = []

    for index, period in enumerate(periods):
        baseline = values[max(0, index - config.window_months): index]
        entry: Dict[str, Any] = {
            "period": period,
            "article_count": values[index],
            "is_partial": period in partial,
        }

        if len(baseline) < config.min_baseline_months:
            entry.update(_no_baseline(len(baseline), "BASELINE_KURANG"))
            rows.append(entry)
            continue

        median = float(statistics.median(baseline))
        mad = float(statistics.median([abs(value - median) for value in baseline]))
        scale = config.mad_scale * mad

        if scale == 0:
            entry.update(_no_baseline(len(baseline), "SKALA_NOL"))
            entry["baseline_median"] = round(median, 2)
            entry["baseline_mad"] = round(mad, 2)
            rows.append(entry)
            continue

        z = (values[index] - median) / scale
        entry.update(
            {
                "z_score": round(z, 2),
                "severity": _severity(z, config.severity),
                "baseline_median": round(median, 2),
                "baseline_mad": round(mad, 2),
                "baseline_n": len(baseline),
                "method": "robust_z_median_mad",
                "window_months": config.window_months,
            }
        )
        rows.append(entry)

        if z > 0 and not entry["is_partial"]:
            spikes.append(dict(entry))

    if config.dedupe_consecutive and spikes:
        spikes = _dedupe_consecutive(spikes, periods)

    spikes.sort(key=lambda item: item["z_score"], reverse=True)
    return AnomalyReport(
        monthly_counts=counts,
        series=pd.DataFrame(rows),
        spikes=tuple(spikes[: config.top_n]),
        partial_periods=tuple(sorted(partial)),
        config=config,
    )


def _no_baseline(count: int, severity: str) -> Dict[str, Any]:
    return {
        "z_score": None,
        "severity": severity,
        "baseline_median": None,
        "baseline_mad": None,
        "baseline_n": count,
    }


def _severity(z: float, thresholds: Dict[str, float]) -> str:
    for label, threshold in sorted(thresholds.items(), key=lambda kv: kv[1], reverse=True):
        if z >= float(threshold):
            return label
    return "NORMAL"


def _month_bounds(period: str) -> Tuple[date, date]:
    year, month = (int(part) for part in period.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _partial_periods(
    periods: List[str], first: Optional[date], last: Optional[date]
) -> set:
    """Bulan yang datanya tidak menutup satu bulan penuh."""
    partial = set()
    if first and periods:
        start, _ = _month_bounds(periods[0])
        if first > start:
            partial.add(periods[0])
    if last and periods:
        _, end = _month_bounds(periods[-1])
        if last < end:
            partial.add(periods[-1])
    return partial


def _calendar_months(first_period: str, last_period: str) -> List[str]:
    """Semua bulan kalender antara dua periode, termasuk yang tanpa artikel."""
    start_year, start_month = (int(part) for part in first_period.split("-"))
    end_year, end_month = (int(part) for part in last_period.split("-"))
    months: List[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _fill_gaps(counts: Dict[str, int]) -> Dict[str, int]:
    """
    Isi bulan kosong dengan 0.

    Tanpa ini jendela baseline melompati bulan kosong, sehingga lonjakan
    musiman tampak lebih tajam daripada kenyataan.
    """
    if not counts:
        return {}
    periods = sorted(counts)
    return {
        period: int(counts.get(period, 0))
        for period in _calendar_months(periods[0], periods[-1])
    }


def _dedupe_consecutive(
    spikes: List[Dict[str, Any]], periods: List[str]
) -> List[Dict[str, Any]]:
    """Bulan berurutan dengan z tinggi biasanya satu peristiwa; simpan puncaknya."""
    order = {period: index for index, period in enumerate(periods)}
    runs: List[Dict[str, Any]] = []
    last_index: Optional[int] = None
    for spike in spikes:
        index = order[spike["period"]]
        if last_index is not None and index - last_index == 1:
            if spike["z_score"] > runs[-1]["z_score"]:
                runs[-1] = spike
            last_index = index
            continue
        runs.append(spike)
        last_index = index
    return runs


def _empty_series() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "period",
            "article_count",
            "is_partial",
            "z_score",
            "severity",
            "baseline_median",
            "baseline_mad",
            "baseline_n",
        ]
    )

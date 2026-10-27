"""
Deteksi ledakan wacana per entitas (Kleinberg dua keadaan).

Model: setiap bulan punya laju dasar `p0` dan laju ledakan `p0 * ratio`.
Urutan keadaan terbaik dicari dengan Viterbi, dengan penalti `gamma` setiap
kali keadaan berubah. Penalti itulah inti metode Kleinberg: tanpa biaya
perpindahan, setiap naik-turun kecil akan dianggap ledakan terpisah.

Kenapa bukan ambang z sederhana: z menjawab "bulan ini tidak biasa untuk
korpus", sedangkan burst menjawab "entitas ini sedang naik pada bulan-bulan
berurutan" — dua pertanyaan berbeda dan keduanya dibutuhkan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import poisson

from ..core.anomaly import monthly_counts
from ..io.bundle import DataBundle


@dataclass(frozen=True)
class BurstConfig:
    gamma: float = 2.0
    burst_ratio: float = 2.0
    min_articles: int = 20
    min_months: int = 2

    def __post_init__(self) -> None:
        if self.gamma < 0:
            raise ValueError("gamma tidak boleh negatif")
        if self.burst_ratio <= 1.0:
            raise ValueError("burst_ratio harus > 1")


@dataclass(frozen=True)
class BurstReport:
    bursts: pd.DataFrame
    months: Tuple[str, ...]
    config: BurstConfig

    def as_dict(self) -> Dict[str, Any]:
        return {
            "months": list(self.months),
            "bursts": self.bursts.to_dict(orient="records"),
            "config": {
                "gamma": self.config.gamma,
                "burst_ratio": self.config.burst_ratio,
                "min_articles": self.config.min_articles,
                "min_months": self.config.min_months,
            },
            "method": "kleinberg_two_state_viterbi",
        }


def entity_monthly_counts(bundle: DataBundle) -> pd.DataFrame:
    """Matriks entitas x bulan berisi jumlah artikel unik per bulan."""
    months = tuple(sorted(monthly_counts(bundle)))
    if not months or bundle.mentions.empty:
        return pd.DataFrame()

    published = pd.to_datetime(bundle.articles["published_at"], format="ISO8601", utc=True)
    article_month = dict(
        zip(bundle.articles["article_id"].astype(str), published.dt.strftime("%Y-%m"))
    )
    frame = bundle.mentions[["article_id", "entity_id"]].astype(str).drop_duplicates()
    frame["month"] = frame["article_id"].map(article_month)
    frame = frame.dropna(subset=["month"])

    table = (
        frame.groupby(["entity_id", "month"])["article_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=list(months), fill_value=0)
    )
    return table


def detect_bursts(
    bundle: DataBundle, config: Optional[BurstConfig] = None
) -> BurstReport:
    """Cari rentang bulan dengan laju di atas dasar untuk setiap entitas."""
    config = config or BurstConfig()
    table = entity_monthly_counts(bundle)
    if table.empty:
        return BurstReport(pd.DataFrame(), (), config)

    months = tuple(str(column) for column in table.columns)
    rows: List[Dict[str, Any]] = []

    for entity_id, series in table.iterrows():
        values = series.to_numpy(dtype=float)
        if values.sum() < config.min_articles:
            continue
        states = _viterbi(values, config)
        rows.extend(_runs(entity_id, months, values, states, config))

    frame = pd.DataFrame(
        rows,
        columns=[
            "entity_id",
            "start",
            "end",
            "months",
            "articles",
            "peak_month",
            "peak_articles",
            "base_rate",
            "burst_rate",
            "lift",
        ],
    )
    if not frame.empty:
        frame = frame.sort_values(
            ["lift", "articles", "entity_id"], ascending=[False, False, True]
        ).reset_index(drop=True)
    return BurstReport(frame, months, config)


def _viterbi(values: np.ndarray, config: BurstConfig) -> np.ndarray:
    """Urutan keadaan 0/1 yang paling mungkin untuk satu deret bulanan."""
    base = float(values.mean())
    if base <= 0:
        return np.zeros(values.size, dtype=int)
    rates = np.array([base, base * config.burst_ratio])

    emissions = np.empty((values.size, 2))
    for state in range(2):
        emissions[:, state] = _poisson_logpmf(values, rates[state])

    score = emissions[0].copy()
    back = np.zeros((values.size, 2), dtype=int)
    for step in range(1, values.size):
        for state in range(2):
            stay = score[state]
            switch = score[1 - state] - config.gamma
            if stay >= switch:
                best, origin = stay, state
            else:
                best, origin = switch, 1 - state
            score[state] = emissions[step, state] + best
            back[step, state] = origin

    states = np.zeros(values.size, dtype=int)
    states[-1] = int(np.argmax(score))
    for step in range(values.size - 1, 0, -1):
        states[step - 1] = back[step, states[step]]
    return states


def _poisson_logpmf(values: np.ndarray, rate: float) -> np.ndarray:
    return poisson.logpmf(values, max(rate, 1e-9))


def _runs(
    entity_id: str,
    months: Tuple[str, ...],
    values: np.ndarray,
    states: np.ndarray,
    config: BurstConfig,
) -> List[Dict[str, Any]]:
    """Rentang keadaan 1 yang memenuhi durasi minimum."""
    rows: List[Dict[str, Any]] = []
    start: Optional[int] = None

    for index, state in enumerate(states):
        if state == 1 and start is None:
            start = index
        elif state == 0 and start is not None:
            rows.extend(_emit(entity_id, months, values, start, index - 1, config))
            start = None
    if start is not None:
        rows.extend(_emit(entity_id, months, values, start, values.size - 1, config))
    return rows


def _emit(
    entity_id: str,
    months: Tuple[str, ...],
    values: np.ndarray,
    start: int,
    end: int,
    config: BurstConfig,
) -> List[Dict[str, Any]]:
    length = end - start + 1
    if length < config.min_months:
        return []

    window = values[start : end + 1]
    base = float(values.mean())
    burst_rate = float(window.mean())
    peak = int(np.argmax(window))
    return [
        {
            "entity_id": entity_id,
            "start": months[start],
            "end": months[end],
            "months": length,
            "articles": int(window.sum()),
            "peak_month": months[start + peak],
            "peak_articles": int(window[peak]),
            "base_rate": round(base, 2),
            "burst_rate": round(burst_rate, 2),
            "lift": round(burst_rate / base, 3) if base else None,
        }
    ]

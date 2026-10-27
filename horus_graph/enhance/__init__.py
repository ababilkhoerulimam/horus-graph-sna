"""
Peningkatan standar enterprise: uji null, bootstrap, topologi, burst, turnover.

Nama-nama di bawah diimpor malas. Alasannya terukur: `bursts` menyeret
`scipy.stats`, dan `scipy.stats` sendiri 5 detik pada impor pertama di Windows —
lebih lama daripada seluruh perhitungan jaringan. API hanya butuh
`reporting_block`, jadi menahan sisanya sampai benar-benar dipanggil menghemat
waktu start yang jauh lebih besar daripada yang bisa dihemat artefak pra-hitung.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any, Dict

_LAZY: Dict[str, str] = {
    "BootstrapResult": ".bootstrap",
    "BurstConfig": ".bursts",
    "BurstReport": ".bursts",
    "NullModelResult": ".nullmodel",
    "TopologyProfile": ".topology",
    "adjusted_rand_index": ".stats",
    "bootstrap_network": ".bootstrap",
    "degree_preserving_null": ".nullmodel",
    "detect_bursts": ".bursts",
    "empirical_p_value": ".stats",
    "entity_monthly_counts": ".bursts",
    "epoch_turnover": ".turnover",
    "reporting_block": ".reporting",
    "topology_profile": ".topology",
    "turnover_summary": ".turnover",
    "two_sided_p_value": ".stats",
    "z_score": ".stats",
}

__all__ = list(_LAZY)

if TYPE_CHECKING:  # agar pemeriksa tipe tetap melihat bentuk aslinya
    from .bootstrap import BootstrapResult, bootstrap_network
    from .bursts import BurstConfig, BurstReport, detect_bursts, entity_monthly_counts
    from .nullmodel import NullModelResult, degree_preserving_null
    from .reporting import reporting_block
    from .stats import adjusted_rand_index, empirical_p_value, two_sided_p_value, z_score
    from .topology import TopologyProfile, topology_profile
    from .turnover import epoch_turnover, turnover_summary


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"modul {__name__!r} tidak punya atribut {name!r}")
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value  # kunjungan berikutnya tidak lewat __getattr__ lagi
    return value


def __dir__() -> list[str]:
    return sorted(__all__)

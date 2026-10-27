"""
Blok pelaporan wajib.

Setiap angka yang keluar dari engine seharusnya bisa dipertanggungjawabkan
tanpa membuka kode: populasi apa, ambang apa, metode apa, apa yang tidak
tersedia, dan seberapa halus resolusi uji yang dipakai. Blok ini menyusunnya
menjadi satu objek yang bisa ditempel apa adanya ke laporan atau UI.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import __version__
from ..core.build import NetworkBundle
from ..io.bundle import DataBundle
from .bootstrap import BootstrapResult
from .nullmodel import NullModelResult
from .topology import TopologyProfile


def reporting_block(
    bundle: DataBundle,
    network: NetworkBundle,
    *,
    null: Optional[NullModelResult] = None,
    bootstrap: Optional[BootstrapResult] = None,
    topology: Optional[TopologyProfile] = None,
    seed: int = 42,
) -> Dict[str, Any]:
    """Fakta yang wajib ikut bila angka engine ini dikutip di luar."""
    provenance = network.provenance()
    backbone = network.backbone

    block: Dict[str, Any] = {
        "software": {"name": "horus-graph", "version": __version__},
        "contract": {
            "version": bundle.manifest.contract_version,
            "dataset_id": bundle.manifest.dataset_id,
            "snapshot_at": bundle.manifest.snapshot_at.isoformat(),
            "date_range": [
                str(bundle.manifest.date_range.start),
                str(bundle.manifest.date_range.end),
            ],
            "timezone": bundle.manifest.timezone,
        },
        "population": {
            "articles": len(bundle.articles),
            "entities": len(bundle.entities),
            "mentions": len(bundle.mentions),
            "dropped_mentions": network.cooccurrence.unknown_mentions,
            "entities_with_mentions": int((network.cooccurrence.node_articles > 0).sum()),
        },
        "parameters": {
            "min_support": backbone.min_support,
            "min_npmi": backbone.min_npmi,
            "rescue_isolated": backbone.rescue_isolated,
            "rescued_edges": backbone.added_for_support,
            "seed": seed,
        },
        "metrics": dict(provenance["metrics"]),
        "layers": dict(network.layers),
        "limitations": _limitations(bundle, network, null),
    }

    if null is not None:
        block["inference"] = {
            "null_model": null.as_dict(),
            "p_value_resolution": round(1.0 / (null.resamples + 1), 4) if null.resamples else None,
        }
    if bootstrap is not None:
        block.setdefault("inference", {})["bootstrap"] = bootstrap.as_dict()
    if topology is not None:
        block["topology"] = topology.as_dict()

    return block


def _limitations(
    bundle: DataBundle, network: NetworkBundle, null: Optional[NullModelResult]
) -> List[str]:
    notes: List[str] = [
        "Ko-okurensi mengukur kebersamaan penyebutan dalam artikel, bukan hubungan kausal.",
        "Ambang support dan NPMI adalah pilihan analis; angka tanpa ambang ini tidak sebanding.",
    ]

    if network.layers.get("transmission") == "awaiting_input":
        notes.append(
            "Lapisan transmisi belum tersedia: alpha Hawkes, lead time, dan rute kawat "
            "tidak dilaporkan (bukan nol)."
        )
    if network.layers.get("sentiment") == "awaiting_input":
        notes.append(
            "Lapisan sentimen belum tersedia: stance dan peringkat sentimen tidak "
            "dilaporkan (bukan netral)."
        )
    if network.backbone.added_for_support:
        notes.append(
            f"{network.backbone.added_for_support} edge ditambahkan hanya untuk menjaga "
            "konektivitas dan tidak lolos ambang; edge ini ditandai `rescued`."
        )
    if _date_only(bundle):
        notes.append(
            "`published_at` hanya memiliki presisi tanggal; analisis bulanan memakai "
            "tanggal tersebut tanpa asumsi jam."
        )
    if null is not None and null.resamples:
        notes.append(
            f"p-value empiris beresolusi 1/{null.resamples + 1}; nilai minimum yang bisa "
            "dilaporkan adalah batas resolusi, bukan bukti kemustahilan."
        )
    return notes


def _date_only(bundle: DataBundle) -> bool:
    if bundle.articles.empty:
        return False
    values = bundle.articles["published_at"].astype(str)
    return bool(values.str.endswith("T00:00:00Z").all())

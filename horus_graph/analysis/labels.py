"""
Evaluasi peringkat terhadap label eksternal (JSONL).

Semua angka lain di sistem ini mengukur konsistensi internal: NPMI terhadap
null, peringkat terhadap varian lain. Tidak satu pun menjawab "apakah urutan
ini benar". Label manual adalah satu-satunya pemeriksaan dari luar, dan karena
itu ia hidup di berkas terpisah — bukan di dalam bundle, supaya label tidak
ikut berubah saat korpus diperbarui.

Format satu baris:
    {"ranking": "brokers", "expected": ["Egy Maulana Vikri", "Marc Klok"]}
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from ..core.build import NetworkBundle
from .ranking import top_brokers

ENV_VAR = "HORUS_LABELS"

# Satu tempat untuk setiap peringkat yang boleh dievaluasi. Peringkat yang
# tidak terdaftar di sini tidak bisa dievaluasi — bukan dievaluasi dengan
# fungsi tebakan.
RANKINGS: Dict[str, Callable[[NetworkBundle, int], List[str]]] = {
    "brokers": lambda network, k: [row["id"] for row in top_brokers(network, limit=k)],
}


def load_labels(path: Path) -> List[Dict[str, Any]]:
    """Baca JSONL; baris kosong dan baris rusak dilewati, bukan menggagalkan."""
    records: List[Dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def evaluate(
    network: NetworkBundle,
    records: Iterable[Dict[str, Any]],
    k: int = 10,
    resolve: Optional[Callable[[NetworkBundle, str], Optional[str]]] = None,
) -> Dict[str, Any]:
    """
    precision@k, recall@k, dan cakupan label yang bisa dievaluasi.

    `coverage` adalah porsi baris label yang benar-benar dievaluasi. Label yang
    menunjuk entitas tak dikenal dilewati dan dilaporkan, bukan dihitung sebagai
    kesalahan peringkat — itu kesalahan katalog.
    """
    resolver = resolve or _default_resolve
    precisions: List[float] = []
    recalls: List[float] = []
    skipped: List[str] = []
    total = 0
    for record in records:
        total += 1
        name = str(record.get("ranking") or "")
        expected_raw = record.get("expected") or []
        expected = [resolver(network, str(item)) for item in expected_raw]
        if name not in RANKINGS or not expected or any(item is None for item in expected):
            skipped.append(name or "(tanpa nama)")
            continue
        predicted = RANKINGS[name](network, k)
        hits = len(set(predicted) & {item for item in expected if item})
        denominator = max(1, min(k, len(predicted)))
        precisions.append(hits / denominator)
        recalls.append(hits / len(set(item for item in expected if item)))

    evaluated = len(precisions)
    return {
        "status": "ready" if evaluated else "insufficient",
        "k": int(k),
        "labelled": total,
        "evaluated": evaluated,
        "coverage": None if total == 0 else round(evaluated / total, 4),
        "precision_at_k": None if not precisions else round(sum(precisions) / evaluated, 4),
        "recall_at_k": None if not recalls else round(sum(recalls) / evaluated, 4),
        "skipped": skipped,
    }


def evaluate_from_env(
    network: NetworkBundle, k: int = 10
) -> Dict[str, Any]:
    """Evaluasi dari `HORUS_LABELS`; tanpa variabel itu, statusnya menyatakan itu."""
    path = os.environ.get(ENV_VAR)
    if not path:
        return {
            "status": "no_labels",
            "reason": f"{ENV_VAR} tidak diset: tidak ada label eksternal untuk dievaluasi",
            "k": int(k),
            "labelled": 0,
            "evaluated": 0,
            "coverage": None,
            "precision_at_k": None,
            "recall_at_k": None,
            "skipped": [],
        }
    records = load_labels(Path(path))
    return evaluate(network, records, k=k)


def _default_resolve(network: NetworkBundle, query: str) -> Optional[str]:
    from .resolve import resolve_entity

    return resolve_entity(network, query)
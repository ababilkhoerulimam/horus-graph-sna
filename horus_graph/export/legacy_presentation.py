"""
Ekstraksi metadata tampilan dari repo lama (satu kali, saat migrasi).

Konten yang hari ini tertanam di `web/static/index.html` — biografi entitas dan
narasi per tahun — dipindahkan ke berkas presentasi yang menyertai bundle.
Setelah itu repo ini tidak lagi menyimpan prosa domain apa pun.

Pengurai di sini sengaja sederhana: kedua blok sumbernya adalah object literal
JavaScript berisi string berkutip ganda, tanpa interpolasi. Kalau bentuknya
berubah, ekstraksi gagal keras dengan pesan jelas — lebih baik daripada diam-diam
menghasilkan teks kosong.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from ..contract.models import (
    ClusterStyle,
    EgoStyle,
    EntityTypeStyle,
    Presentation as PresentationMeta,
)

_DESCRIPTIONS = re.compile(
    r"const\s+ENTITY_DESCRIPTIONS\s*=\s*\{(?P<body>.*?)\n\s*\};", re.DOTALL
)
_MILESTONES = re.compile(
    r"const\s+MILESTONES\s*=\s*\{(?P<body>.*?)\n\s*\};", re.DOTALL
)
_CLUSTER_LABELS = re.compile(
    r"const\s+clusterLabels\s*=\s*\{(?P<body>.*?)\n\s*\};", re.DOTALL
)
_ORBIT_TIERS = re.compile(
    r"const\s+ORBIT_TIERS\s*=\s*\[(?P<body>.*?)\n\s*\];", re.DOTALL
)
_ORBIT_LABEL = re.compile(r"label\s*:\s*\"((?:[^\"\\]|\\.)*)\"")
_STRING_ENTRY = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
_MILESTONE_ENTRY = re.compile(r"(\d{4}|null)\s*:\s*\"((?:[^\"\\]|\\.)*)\"")

# Label cincin 0 tidak ada di visualizer lama (di sana cincin 0 adalah simpul
# pusat, bukan cincin). Nama netral ini menjaga indeks tetap lurus.
RING_ZERO_LABEL = "Pusat"


def extract_from_legacy_repo(repo: Path | str, domain: Any) -> Dict[str, Any]:
    """Susun payload presentasi dari `config/domain.yaml` + `index.html`."""
    index = Path(repo) / "web" / "static" / "index.html"
    descriptions = extract_descriptions(index)
    narratives = extract_milestones(index)
    cluster_labels = extract_cluster_labels(index)
    orbit_tiers = extract_orbit_tiers(index)

    entity_types = _entity_types(domain)
    clusters = _clusters(domain, cluster_labels)

    payload: Dict[str, Any] = {
        "title": f"Analisis Jaringan: {domain.club_display}",
        "ego": {"id": domain.club_id, "label": domain.club_display},
        "entity_types": entity_types,
        "clusters": clusters,
        "orbit_tiers": [RING_ZERO_LABEL, *orbit_tiers],
        "epoch_narratives": narratives,
        "entity_descriptions": descriptions,
    }
    return payload


def extract_cluster_labels(index: Path) -> Dict[str, str]:
    raw = _parse_block(index, _CLUSTER_LABELS, "clusterLabels")
    pairs = _STRING_ENTRY.findall(raw)
    return {_unescape(key): _unescape(value) for key, value in pairs}


def extract_orbit_tiers(index: Path) -> list[str]:
    raw = _parse_block(index, _ORBIT_TIERS, "ORBIT_TIERS")
    labels = [_unescape(value) for value in _ORBIT_LABEL.findall(raw)]
    if not labels:
        raise ValueError(f"{index}: ORBIT_TIERS tidak memuat satu pun label")
    return labels


def extract_descriptions(index: Path) -> Dict[str, str]:
    return _parse_string_block(index, _DESCRIPTIONS, "ENTITY_DESCRIPTIONS")


def extract_milestones(index: Path) -> Dict[str, str]:
    """Narasi per tahun; entri `null` (semua waktu) dibuang."""
    raw = _parse_block(index, _MILESTONES, "MILESTONES")
    result: Dict[str, str] = {}
    for key, value in _MILESTONE_ENTRY.findall(raw):
        if key == "null":
            continue
        result[key] = _unescape(value)
    if not result:
        raise ValueError(f"{index}: MILESTONES tidak menghasilkan satu pun narasi")
    return result


def _parse_string_block(index: Path, pattern: re.Pattern, name: str) -> Dict[str, str]:
    raw = _parse_block(index, pattern, name)
    pairs = _STRING_ENTRY.findall(raw)
    if not pairs:
        raise ValueError(f"{index}: {name} tidak memuat pasangan kunci-nilai")
    return {_unescape(key): _unescape(value) for key, value in pairs}


def _parse_block(index: Path, pattern: re.Pattern, name: str) -> str:
    if not index.exists():
        raise FileNotFoundError(f"berkas visualizer lama tidak ada: {index}")
    text = index.read_text(encoding="utf-8")
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"{index}: blok {name} tidak ditemukan")
    return match.group("body")


def _unescape(value: str) -> str:
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _entity_types(domain: Any) -> list[Dict[str, Any]]:
    """Satu gaya per tipe; warna diambil dari entitas pertama bertipe itu."""
    seen: Dict[str, Optional[str]] = {}
    for entity in domain.entities:
        if entity.entity_type not in seen:
            seen[entity.entity_type] = getattr(entity, "color", None)
    return [
        {"id": type_id, "label": type_id, "color": color}
        for type_id, color in seen.items()
    ]


def _clusters(domain: Any, labels: Dict[str, str]) -> list[Dict[str, Any]]:
    seen: Dict[str, Optional[str]] = {}
    for entity in domain.entities:
        cluster = getattr(entity, "cluster", None)
        if cluster and cluster not in seen:
            seen[cluster] = getattr(entity, "color", None)
    return [
        {"id": key, "label": labels.get(key, key), "color": color}
        for key, color in seen.items()
    ]


def load_presentation_file(path: Path | str) -> Dict[str, Any]:
    """Baca berkas presentasi; `entity_descriptions` tetap sebagai kunci terpisah."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def split_payload(payload: Dict[str, Any]) -> tuple[PresentationMeta, Dict[str, str]]:
    """Pisahkan metadata tampilan dari deskripsi per entitas."""
    data = dict(payload)
    descriptions = {
        str(key): str(value)
        for key, value in (data.pop("entity_descriptions", None) or {}).items()
    }
    return PresentationMeta(**data), descriptions

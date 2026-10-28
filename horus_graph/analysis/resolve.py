"""
Pencocokan nama entitas.

Pengguna mengetik "egy", "Egy Maulana", atau "EGY MAULANA VIKRI". Resolusi harus
deterministik dan tidak boleh menebak: urutan pencarian tetap (id persis, id
ternormalisasi, label, alias, lalu substring), dan bila satu lapis menghasilkan
lebih dari satu kandidat jawabannya None — bukan kandidat pertama menurut urutan
baris, yang berubah setiap kali bundle ditulis ulang.

Normalisasi (NFKD, buang aksen, casefold, tanda baca jadi spasi) membuat
"Égy Maulana-Vikri" dan "egy maulana vikri" pertanyaan yang sama.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from ..core.build import NetworkBundle

# Hanya huruf kecil, angka, dan spasi yang bertahan; sisanya pemisah.
_SEPARATORS = re.compile(r"[^0-9a-z]+")


def normalize(text: object) -> str:
    """Bentuk pencarian: tanpa aksen, huruf kecil, tanda baca jadi spasi."""
    if not isinstance(text, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _SEPARATORS.sub(" ", without_marks.casefold()).strip()


def _catalog(
    network: NetworkBundle,
) -> Tuple[List[str], Dict[str, str], Dict[str, str], Dict[str, List[str]]]:
    """Bentuk ternormalisasi dari katalog, dihitung sekali per pencarian."""
    index = [str(entity_id) for entity_id in network.entities.index]
    ids = {entity_id: normalize(entity_id) for entity_id in index}
    labels: Dict[str, str] = {}
    for entity_id in index:
        labels[entity_id] = normalize(network.entities.at[entity_id, "label"])
    aliases = {
        entity_id: [normalize(value) for value in values]
        for entity_id, values in network.aliases.items()
        if entity_id in labels
    }
    return index, ids, labels, aliases


def _matches(network: NetworkBundle, query: object) -> List[str]:
    """
    Semua kandidat pada lapis pencarian pertama yang menghasilkan sesuatu.

    Lapis yang lebih tinggi menang walau lapis bawah punya kandidat: id persis
    selalu mengalahkan substring, supaya menambah entitas baru tidak mengubah
    jawaban untuk kueri lama.
    """
    text = query.strip() if isinstance(query, str) else ""
    if not text:
        return []
    index, ids, labels, aliases = _catalog(network)
    if text in index:
        return [text]

    wanted = normalize(text)
    if not wanted:
        return []

    for tier in (
        [entity_id for entity_id in index if ids[entity_id] == wanted],
        [entity_id for entity_id in index if labels[entity_id] == wanted],
        [entity_id for entity_id in index if wanted in aliases.get(entity_id, ())],
    ):
        if tier:
            return tier

    return [
        entity_id
        for entity_id in index
        if wanted in ids[entity_id]
        or wanted in labels[entity_id]
        or any(wanted in alias for alias in aliases.get(entity_id, ()))
    ]


def resolve_entity(network: NetworkBundle, query: str) -> Optional[str]:
    """Id entitas untuk query, atau None bila tidak ada atau ambigu."""
    found = _matches(network, query)
    return found[0] if len(found) == 1 else None


def resolve_candidates(
    network: NetworkBundle, query: str, limit: int = 5
) -> List[str]:
    """Kandidat saat kueri ambigu; kosong bila jawabannya tunggal atau kosong."""
    found = _matches(network, query)
    return found[: max(0, limit)] if len(found) > 1 else []


def unresolved_share(network: NetworkBundle) -> Dict[str, Any]:
    """
    Porsi entitas yang namanya tidak bisa dipakai mencari dirinya sendiri.

    Diukur pada label katalog, bukan pada kueri pengguna: label ganda, atau
    label yang justru menunjuk entitas lain, membuat entitas itu tidak pernah
    bisa ditemukan lewat namanya — dan itu cacat data, bukan salah ketik.
    """
    index = [str(entity_id) for entity_id in network.entities.index]
    unresolved: List[str] = []
    for entity_id in index:
        found = _matches(network, network.entities.at[entity_id, "label"])
        if len(found) != 1 or found[0] != entity_id:
            unresolved.append(entity_id)

    total = len(index)
    return {
        "entities": total,
        "unresolved": len(unresolved),
        "unresolved_share": None if total == 0 else round(len(unresolved) / total, 4),
        "unresolved_ids": unresolved[:20],
    }
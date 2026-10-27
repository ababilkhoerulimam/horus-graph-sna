"""
Pencocokan nama entitas.

Pengguna mengetik "egy", "Egy Maulana", atau "EGY MAULANA VIKRI". Resolusi harus
deterministik: urutan pencarian tetap (id persis, id case-insensitive, label
persis, lalu substring pada id dan label), dan hasil pertama menang. Tanpa
urutan tetap, dua entitas yang sama-sama cocok membuat hasil berubah-ubah antar
pemanggilan.
"""

from __future__ import annotations

from typing import Optional

from ..core.build import NetworkBundle


def resolve_entity(network: NetworkBundle, query: str) -> Optional[str]:
    """Id entitas untuk `query`, atau `None` bila tidak ada yang cocok."""
    text = (query or "").strip()
    if not text:
        return None

    index = network.entities.index
    if text in index:
        return text

    lowered = text.lower()
    for entity_id in index:
        if entity_id.lower() == lowered:
            return entity_id

    for entity_id in index:
        label = network.entities.at[entity_id, "label"]
        if isinstance(label, str) and label.lower() == lowered:
            return entity_id

    for entity_id in index:
        label = network.entities.at[entity_id, "label"]
        if lowered in entity_id.lower():
            return entity_id
        if isinstance(label, str) and lowered in label.lower():
            return entity_id

    return None

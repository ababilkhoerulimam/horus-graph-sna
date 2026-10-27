"""
Metadata tampilan: satu-satunya tempat warna, judul, label, dan narasi berasal.

Repo ini tidak boleh memuat nama domain. Yang tersisa di sini hanyalah default
netral — istilah struktural yang berlaku untuk jaringan apa pun ("Simpul",
"Sisi", "Kepadatan"). Begitu sebuah bundle membawa `manifest.presentation`,
seluruh nilai di bawah ditimpa olehnya.

Konsekuensinya: fork repo + bundle baru = tampilan baru, tanpa menyunting kode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd

from .contract.models import (
    ActionRule,
    ClusterStyle,
    EgoStyle,
    EntityTypeStyle,
    Palette,
    Presentation as PresentationMeta,
    RadiusScale,
)
from .io.bundle import DataBundle

# Palet netral: tidak menyiratkan domain apa pun, hanya cukup kontras untuk
# delapan komunitas pertama. Bundle boleh menimpanya sepenuhnya.
NEUTRAL_COLORS: Tuple[str, ...] = (
    "#0EA5E9",
    "#8B5CF6",
    "#10B981",
    "#F59E0B",
    "#EF4444",
    "#EC4899",
    "#14B8A6",
    "#6366F1",
)

DEFAULT_LABELS: Dict[str, str] = {
    "node": "Simpul",
    "nodes": "Simpul",
    "edge": "Sisi",
    "edges": "Sisi",
    "density": "Kepadatan",
    "community": "Komunitas",
    "communities": "Komunitas",
    "component": "Komponen",
    "components": "Komponen",
    "corpus": "Korpus",
    "articles": "Artikel",
    "entities": "Entitas",
}

DEFAULT_WORDING: Dict[str, str] = {
    "empty_anomaly": "Belum ada anomali pada rentang ini.",
    "empty_graph": "Belum ada simpul yang lolos ambang.",
    "no_bundle": (
        "Belum ada bundle data. Letakkan bundle pada data/bundles/ "
        "atau set variabel HORUS_BUNDLE."
    ),
    "boot_error": "Gagal memuat data jaringan.",
    "awaiting_layer": "Lapisan ini belum tersedia.",
}


@dataclass(frozen=True)
class Presentation:
    """Metadata tampilan yang sudah diresolusi, siap dipakai API dan UI."""

    title: str
    subtitle: Optional[str]
    ego: Optional[EgoStyle]
    entity_types: Mapping[str, EntityTypeStyle]
    clusters: Mapping[str, ClusterStyle]
    palette: Palette
    labels: Mapping[str, str]
    wording: Mapping[str, str]
    orbit_tiers: Tuple[str, ...]
    epoch_narratives: Mapping[str, str]
    action_rules: Mapping[str, ActionRule]
    sankey_columns: Tuple[str, ...]
    radius_scale: RadiusScale

    def label(self, key: str, default: Optional[str] = None) -> str:
        return self.labels.get(key, default if default is not None else key)

    def text(self, key: str, default: str = "") -> str:
        return self.wording.get(key, default)

    def entity_type(self, type_id: Optional[str]) -> Optional[EntityTypeStyle]:
        if type_id is None:
            return None
        return self.entity_types.get(type_id)

    def color_for(self, entity_type: Optional[str], index: int = 0) -> str:
        style = self.entity_type(entity_type)
        if style is not None and style.color:
            return style.color
        return _cycle(NEUTRAL_COLORS, index)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "ego": self.ego.model_dump() if self.ego else None,
            "entity_types": [style.model_dump() for style in self.entity_types.values()],
            "clusters": [style.model_dump() for style in self.clusters.values()],
            "palette": self.palette.model_dump(),
            "labels": dict(self.labels),
            "wording": dict(self.wording),
            "orbit_tiers": list(self.orbit_tiers),
            "epoch_narratives": dict(self.epoch_narratives),
            "action_rules": {
                key: rule.model_dump() for key, rule in self.action_rules.items()
            },
            "sankey_columns": list(self.sankey_columns),
            "radius_scale": self.radius_scale.model_dump(),
        }


def resolve_presentation(bundle: DataBundle) -> Presentation:
    """
    Gabungkan metadata bundle dengan default netral.

    Urutan sumber: `manifest.presentation` → `domain` → tabel `entities` →
    default. Ego diambil dari `presentation.ego` bila ada, kalau tidak dari
    `domain.ego_id`; `ego_id` kosong berarti dataset tanpa pusat.
    """
    meta: PresentationMeta = bundle.manifest.presentation or PresentationMeta()
    palette = _resolve_palette(meta)
    entity_types = _resolve_entity_types(meta, bundle.entities, palette)

    return Presentation(
        title=meta.title or bundle.manifest.dataset_id,
        subtitle=meta.subtitle,
        ego=_resolve_ego(meta, bundle),
        entity_types=entity_types,
        clusters=_resolve_clusters(meta, bundle.entities),
        palette=palette,
        labels={**DEFAULT_LABELS, **dict(meta.labels)},
        wording={**DEFAULT_WORDING, **dict(meta.wording)},
        orbit_tiers=tuple(meta.orbit_tiers),
        epoch_narratives=dict(meta.epoch_narratives),
        action_rules=dict(meta.action_rules),
        sankey_columns=tuple(meta.sankey_columns),
        radius_scale=meta.radius_scale or RadiusScale(),
    )


def _resolve_palette(meta: PresentationMeta) -> Palette:
    palette = meta.palette
    if not palette.community:
        palette = palette.model_copy(update={"community": list(NEUTRAL_COLORS)})
    return palette.model_copy(
        update={
            "node": palette.node or "#64748B",
            "ego": palette.ego or "#F59E0B",
            "edge": palette.edge or "#334155",
        }
    )


def _resolve_ego(meta: PresentationMeta, bundle: DataBundle) -> Optional[EgoStyle]:
    if meta.ego is not None:
        label = meta.ego.label or _entity_label(bundle.entities, meta.ego.id)
        return meta.ego.model_copy(update={"label": label})

    ego_id = (bundle.domain.ego_id or "").strip()
    if not ego_id:
        return None
    return EgoStyle(id=ego_id, label=_entity_label(bundle.entities, ego_id))


def _resolve_entity_types(
    meta: PresentationMeta, entities: pd.DataFrame, palette: Palette
) -> Dict[str, EntityTypeStyle]:
    if meta.entity_types:
        return {
            style.id: style.model_copy(
                update={"color": style.color or _cycle(palette.community, index)}
            )
            for index, style in enumerate(meta.entity_types)
        }

    if entities.empty or "entity_type" not in entities.columns:
        return {}

    seen: List[str] = []
    for value in entities["entity_type"].astype(str):
        if value not in seen:
            seen.append(value)
    return {
        type_id: EntityTypeStyle(
            id=type_id, label=type_id, color=_cycle(palette.community, index)
        )
        for index, type_id in enumerate(seen)
    }


def _resolve_clusters(
    meta: PresentationMeta, entities: pd.DataFrame
) -> Dict[str, ClusterStyle]:
    if meta.clusters:
        return {style.id: style for style in meta.clusters}

    if entities.empty or "cluster" not in entities.columns:
        return {}

    values = [str(value) for value in entities["cluster"].dropna().unique()]
    return {value: ClusterStyle(id=value, label=value) for value in sorted(values)}


def _entity_label(entities: pd.DataFrame, entity_id: str) -> str:
    if entities.empty or "entity_id" not in entities.columns:
        return entity_id
    match = entities.loc[entities["entity_id"].astype(str) == entity_id, "label"]
    if match.empty:
        return entity_id
    return str(match.iloc[0])


def _cycle(values: Tuple[str, ...] | List[str], index: int) -> str:
    if not values:
        return "#64748B"
    return values[index % len(values)]

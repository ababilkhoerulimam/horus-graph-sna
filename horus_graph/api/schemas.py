"""
Bentuk respons yang dijanjikan ke klien.

Dua aturan yang dipakai di sini:

1. `extra="allow"` di semua model. Model ini mendokumentasikan kunci yang
   **dijanjikan**, bukan membatasi yang boleh ada. Tanpa itu, satu kunci baru di
   serializer akan hilang diam-diam dari respons — persis kegagalan yang tidak
   terlihat di tes mana pun.
2. Nilai yang bisa tidak terukur diberi `Optional`. Angka yang tidak ada
   dikirim sebagai `null`, bukan `0`, sama seperti di UI.

Endpoint yang bentuknya belum stabil (briefing, provenance, bootstrap) sengaja
tidak diberi model: skemanya akan berubah setiap kali analisis bertambah, dan
skema yang selalu usang lebih buruk daripada tidak ada skema.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class HealthResponse(_Loose):
    status: str
    dataset: str
    snapshot_id: Optional[str] = None
    nodes: int
    edges: int
    density: Optional[float] = None
    contract_version: str
    build_seconds: float
    capabilities: Dict[str, bool]


class DatasetStatusResponse(_Loose):
    dataset: str
    counts: Dict[str, int]
    layers: Dict[str, str]
    root: str
    build_seconds: float


class SnapshotInfo(_Loose):
    snapshot_id: str
    dataset_id: str
    folder: str
    snapshot_at: str
    counts: Dict[str, int] = Field(default_factory=dict)
    title: Optional[str] = None


class DatasetListResponse(_Loose):
    active: Optional[str] = None
    datasets: List[SnapshotInfo]


class KeyEvent(_Loose):
    date: str
    title: str
    description: str
    severity: Optional[str] = None
    related_actors: List[str] = Field(default_factory=list)


class GraphOverviewResponse(_Loose):
    title: str
    subtitle: Optional[str] = None
    ego_node: Optional[str] = None
    ego_label: Optional[str] = None
    total_nodes: int
    total_edges: int
    density: Optional[float] = None
    communities_count: int
    community_sizes: List[int] = Field(default_factory=list)
    modularity: Optional[float] = None
    transitivity: Optional[float] = None
    diameter: Optional[int] = None
    average_path_length: Optional[float] = None
    components: Optional[int] = None
    isolated: Optional[int] = None


class EntitySummary(_Loose):
    id: str
    label: str
    entity_type: str
    aliases: List[str] = Field(default_factory=list)


class EntityIndexResponse(_Loose):
    entities: List[EntitySummary]


class EpochSummary(_Loose):
    id: str
    label: str
    start_year: int
    end_year: int
    nodes: int
    edges: int


class TemporalResponse(_Loose):
    epochs: List[EpochSummary]


class EvidenceItem(_Loose):
    article_id: str
    title: Optional[str] = None
    site: Optional[str] = None
    published_at: Optional[str] = None
    url: Optional[str] = None


class EdgeEvidenceResponse(_Loose):
    source: str
    target: str
    weight: int
    npmi: Optional[float] = None
    rescued: bool
    evidence: List[EvidenceItem]


class BrokerRow(_Loose):
    rank: int
    id: str
    label: str
    entity_type: str
    betweenness: Optional[float] = None
    degree: int


class BrokerRankingResponse(_Loose):
    entity_type: Optional[str] = None
    ranking: List[BrokerRow]


class HoleRow(_Loose):
    id: str
    label: str
    entity_type: str
    burt_constraint: Optional[float] = None
    effective_size: Optional[float] = None
    degree: int


class HoleRankingResponse(_Loose):
    mode: str
    thresholds: Dict[str, Any] = Field(default_factory=dict)
    ranking: List[HoleRow]

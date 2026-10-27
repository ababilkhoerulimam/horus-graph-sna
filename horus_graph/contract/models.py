"""Model kontrak: manifest dan domain yang menyertai setiap bundle."""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

LayerStatus = Literal["ready", "awaiting_input"]


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date


class GeneratorInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    version: Optional[str] = None
    git_sha: Optional[str] = None


class EgoStyle(BaseModel):
    """Simpul pusat, bila dataset punya satu. `None` berarti tidak ada pusat."""

    model_config = ConfigDict(extra="allow")

    id: str
    label: Optional[str] = None
    role: Optional[str] = None


class EntityTypeStyle(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    label: Optional[str] = None
    color: Optional[str] = None
    role_template: Optional[str] = None


class ClusterStyle(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    label: Optional[str] = None
    color: Optional[str] = None


class Palette(BaseModel):
    model_config = ConfigDict(extra="allow")

    community: List[str] = Field(default_factory=list)
    node: Optional[str] = None
    ego: Optional[str] = None
    edge: Optional[str] = None


class ActionRule(BaseModel):
    """Kalimat kartu tindakan untuk satu peran struktural (broker, media, ...)."""

    model_config = ConfigDict(extra="allow")

    title: Optional[str] = None
    body: Optional[str] = None


class RadiusScale(BaseModel):
    model_config = ConfigDict(extra="allow")

    min: float = 11.0
    max: float = 47.0


class Presentation(BaseModel):
    """
    Metadata tampilan. Semua field opsional: engine menyusun default netral
    bila tidak ada, sehingga repo tidak pernah memuat nama domain.
    """

    model_config = ConfigDict(extra="allow")

    title: Optional[str] = None
    subtitle: Optional[str] = None
    ego: Optional[EgoStyle] = None
    entity_types: List[EntityTypeStyle] = Field(default_factory=list)
    clusters: List[ClusterStyle] = Field(default_factory=list)
    palette: Palette = Field(default_factory=Palette)
    orbit_tiers: List[str] = Field(default_factory=list)
    epoch_narratives: Dict[str, str] = Field(default_factory=dict)
    labels: Dict[str, str] = Field(default_factory=dict)
    wording: Dict[str, str] = Field(default_factory=dict)
    action_rules: Dict[str, ActionRule] = Field(default_factory=dict)
    sankey_columns: List[str] = Field(default_factory=list)
    radius_scale: Optional[RadiusScale] = None


class Manifest(BaseModel):
    """metadata yang mengikat seluruh tabel ke satu snapshot."""

    model_config = ConfigDict(extra="allow")

    contract_version: str
    dataset_id: str
    snapshot_at: datetime
    date_range: DateRange
    timezone: str = "UTC"
    counts: Dict[str, int] = Field(default_factory=dict)
    file_sha256: Dict[str, str] = Field(default_factory=dict)
    generator: GeneratorInfo
    dictionary_version: Optional[str] = None
    layers: Dict[str, LayerStatus] = Field(default_factory=dict)
    presentation: Optional[Presentation] = None
    # Diisi engine saat bundle dimuat bila pipeline tidak menuliskannya. Nilai
    # yang ditulis pipeline tidak ditimpa, supaya pipeline tetap pemilik data.
    snapshot_id: Optional[str] = None


class Epoch(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    label: str
    start_year: int
    end_year: int


class Domain(BaseModel):
    """
    Identitas dataset. Engine tidak tahu domain apa pun di luar berkas ini.

    `ego_id` boleh kosong: dataset seperti kebakaran lahan tidak punya satu
    simpul pusat, dan seluruh tampilan punya cabang untuk kasus itu.
    `league` dipertahankan hanya untuk bundle lama; jangan dipakai kode baru —
    label domain kini hidup di `manifest.presentation`.
    """

    model_config = ConfigDict(extra="allow")

    domain_id: str
    ego_id: str = ""
    label: str
    league: Optional[str] = None
    entity_types: List[str] = Field(default_factory=list)
    epochs: List[Epoch] = Field(default_factory=list)
    clusters: List[str] = Field(default_factory=list)

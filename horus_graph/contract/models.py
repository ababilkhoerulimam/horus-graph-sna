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


class Epoch(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    label: str
    start_year: int
    end_year: int


class Domain(BaseModel):
    """Identitas dataset. Engine tidak tahu domain apa pun di luar berkas ini."""

    model_config = ConfigDict(extra="allow")

    domain_id: str
    ego_id: str
    label: str
    league: Optional[str] = None
    entity_types: List[str] = Field(default_factory=list)
    epochs: List[Epoch] = Field(default_factory=list)
    clusters: List[str] = Field(default_factory=list)

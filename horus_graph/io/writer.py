"""Penulisan bundle: parquet sesuai skema kontrak + manifest ber-hash."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..contract import schema
from ..contract.models import DateRange, Domain, GeneratorInfo, LayerStatus, Manifest


def _to_arrow(frame: pd.DataFrame, target: pa.Schema, table: str) -> pa.Table:
    """
    Susun ulang kolom sesuai skema kontrak.

    Kolom wajib harus ada; kolom presentasi opsional (v1.1) ikut ditulis bila
    frame membawanya, dan kolom asing lainnya dibuang.
    """
    missing = [field.name for field in target if field.name not in frame.columns]
    if missing:
        raise ValueError(f"{table}: kolom wajib hilang {missing}")

    fields = list(target)
    ordered = frame[[field.name for field in target]].copy()

    for field in schema.OPTIONAL_COLUMNS.get(table, pa.schema([])):
        if field.name not in frame.columns:
            continue
        fields.append(field)
        ordered[field.name] = _coerce(frame[field.name], field)

    return pa.Table.from_pandas(
        ordered, schema=pa.schema(fields), preserve_index=False
    )


def _coerce(series: pd.Series, field: pa.Field) -> pd.Series:
    """Samakan dtype pandas agar kolom opsional boleh berisi null."""
    if pa.types.is_string(field.type):
        return series.astype("string")
    if pa.types.is_integer(field.type):
        return pd.to_numeric(series, errors="coerce").astype("Int64")
    if pa.types.is_boolean(field.type):
        return series.astype("boolean")
    return series


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_bundle(
    root: Path | str,
    *,
    frames: Dict[str, pd.DataFrame],
    domain: Domain,
    dataset_id: str,
    date_range: tuple[date, date],
    generator: str,
    generator_version: Optional[str] = None,
    generator_git_sha: Optional[str] = None,
    dictionary_version: Optional[str] = None,
    backbone: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> Manifest:
    """Tulis bundle lengkap. `frames` boleh hanya berisi tabel yang tersedia.

    `backbone` menyimpan ambang seleksi edge milik bundle ini
    (`min_support`, `min_npmi`, `rescue_isolated`). Bila tidak diisi, engine
    memakai default yang sama seperti sebelumnya.
    """
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    (target / "layers").mkdir(exist_ok=True)

    manifest_extra = dict(extra or {})
    if backbone is not None:
        manifest_extra["backbone"] = backbone

    counts: Dict[str, int] = {}
    hashes: Dict[str, str] = {}
    layers: Dict[str, LayerStatus] = {}

    for table, (relative, table_schema, required) in schema.TABLES.items():
        frame = frames.get(table)
        if frame is None or (required is False and frame.empty):
            if table in ("transmission", "sentiment"):
                layers[table] = "awaiting_input"
            continue
        arrow = _to_arrow(frame, table_schema, table)
        path = target / relative
        pq.write_table(arrow, path, compression="zstd")
        counts[table] = len(frame)
        hashes[relative] = _sha256(path)
        if table in ("transmission", "sentiment"):
            layers[table] = "ready"

    manifest = Manifest(
        contract_version=schema.CONTRACT_VERSION,
        dataset_id=dataset_id,
        snapshot_at=datetime.now(timezone.utc),
        date_range=DateRange(start=date_range[0], end=date_range[1]),
        timezone="UTC",
        counts=counts,
        file_sha256=hashes,
        generator=GeneratorInfo(
            name=generator,
            version=generator_version,
            git_sha=generator_git_sha,
        ),
        dictionary_version=dictionary_version,
        layers=layers,
        **manifest_extra,
    )

    (target / schema.DOMAIN).write_text(
        domain.model_dump_json(indent=2), encoding="utf-8"
    )
    (target / schema.MANIFEST).write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return manifest

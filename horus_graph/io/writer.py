"""Penulisan bundle: parquet sesuai skema kontrak + manifest ber-hash."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..contract import schema
from ..contract.models import Domain, Manifest


def _to_arrow(frame: pd.DataFrame, target: pa.Schema, table: str) -> pa.Table:
    """Susun ulang kolom sesuai skema kontrak; kolom tambahan dibuang."""
    missing = [field.name for field in target if field.name not in frame.columns]
    if missing:
        raise ValueError(f"{table}: kolom wajib hilang {missing}")
    ordered = frame[[field.name for field in target]]
    return pa.Table.from_pandas(ordered, schema=target, preserve_index=False)


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
    extra: Optional[dict] = None,
) -> Manifest:
    """Tulis bundle lengkap. `frames` boleh hanya berisi tabel yang tersedia."""
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    (target / "layers").mkdir(exist_ok=True)

    counts: Dict[str, int] = {}
    hashes: Dict[str, str] = {}
    layers: Dict[str, str] = {}

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
        date_range={"start": date_range[0], "end": date_range[1]},
        timezone="UTC",
        counts=counts,
        file_sha256=hashes,
        generator={
            "name": generator,
            "version": generator_version,
            "git_sha": generator_git_sha,
        },
        dictionary_version=dictionary_version,
        layers=layers,
        **(extra or {}),
    )

    (target / schema.DOMAIN).write_text(
        domain.model_dump_json(indent=2), encoding="utf-8"
    )
    (target / schema.MANIFEST).write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return manifest

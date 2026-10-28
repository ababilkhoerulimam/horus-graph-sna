"""
Validator bundle: menolak bundle yang melanggar kontrak, menerima yang patuh.

Prinsip yang sama dengan validator artefak di horus-agent: validator tidak
memperbaiki apa pun. Ia mengembalikan daftar temuan supaya pipeline (Kaggle)
bisa diperbaiki di sumbernya, bukan ditambal di engine.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pyarrow.parquet as pq
from pydantic import ValidationError

from . import schema
from .models import Domain, Manifest

SENTIMENT_SUM_TOLERANCE = 1.0
# Dua artikel bisa jadi rilis yang memang diringkas dua kali; tiga dengan judul
# identik di hari yang sama sudah berpola.
SYNDICATION_MIN_COPIES = 3


@dataclass
class Finding:
    level: str  # error | warn
    code: str
    table: str
    message: str


def _error(code: str, table: str, message: str) -> Finding:
    return Finding("error", code, table, message)


def _warn(code: str, table: str, message: str) -> Finding:
    return Finding("warn", code, table, message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path, table: str, findings: List[Finding]) -> Optional[dict]:
    if not path.exists():
        findings.append(_error(f"{table}_missing", table, f"Berkas tidak ditemukan: {path}"))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(_error(f"{table}_unreadable", table, f"Gagal membaca {path}: {exc}"))
        return None


def _read_table(
    path: Path, table: str, required_schema, findings: List[Finding]
) -> Optional[pd.DataFrame]:
    if not path.exists():
        findings.append(_error("file_missing", table, f"Tabel wajib tidak ada: {path.name}"))
        return None
    try:
        arrow = pq.read_table(path)
    except Exception as exc:
        findings.append(_error("file_unreadable", table, f"Parquet tidak bisa dibaca: {exc}"))
        return None

    missing = schema.missing_columns(arrow.schema, required_schema)
    if missing:
        findings.append(
            _error("schema_missing_columns", table, f"Kolom wajib hilang: {missing}")
        )
        return None
    return arrow.to_pandas()


def _distinct(frame: pd.DataFrame, column: str) -> set:
    """
    Nilai unik satu kolom sebagai `set` Python.

    `set(frame[column])` mengekstrak satu skalar Arrow per baris. Pada kolom
    191 ribu baris di bundle emas itu 0,24 detik; `unique()` lalu `tolist()`
    mengonversi sekali di sisi Arrow dan memakan 0,008 detik untuk hasil yang
    sama. Perbedaannya berlipat di setiap kolom yang diperiksa.
    """
    return set(frame[column].dropna().unique().tolist())


def _check_primary_key(frame: pd.DataFrame, table: str, findings: List[Finding]) -> None:
    keys = schema.PRIMARY_KEYS[table]
    duplicated = int(frame.duplicated(subset=keys).sum())
    if duplicated:
        findings.append(
            _error("primary_key_duplicate", table, f"{duplicated} baris duplikat pada {keys}")
        )


def _check_foreign_keys(
    frame: pd.DataFrame,
    table: str,
    column: str,
    allowed: set,
    target: str,
    findings: List[Finding],
) -> None:
    orphans = _distinct(frame, column) - allowed
    if orphans:
        findings.append(
            _error(
                "foreign_key_violation",
                table,
                f"{len(orphans)} nilai {column} tidak ada di {target}: {sorted(orphans)[:5]}",
            )
        )


def _check_counts(frame: pd.DataFrame, table: str, manifest: Manifest, findings: List[Finding]) -> None:
    recorded = manifest.counts.get(table)
    if recorded is None:
        findings.append(_warn("count_missing", table, f"manifest.counts tidak memuat '{table}'"))
    elif int(recorded) != len(frame):
        findings.append(
            _error("count_mismatch", table, f"manifest={recorded} != baris aktual={len(frame)}")
        )


def _check_articles(frame: pd.DataFrame, manifest: Manifest, findings: List[Finding]) -> None:
    if frame.empty:
        findings.append(_error("empty_table", "articles", "Tabel articles kosong"))
        return

    published = pd.to_datetime(
        frame["published_at"], errors="coerce", utc=True, format="ISO8601"
    )
    invalid = int(published.isna().sum())
    if invalid:
        findings.append(
            _error("published_at_invalid", "articles", f"{invalid} nilai tidak bisa diparse")
        )
        return

    start = pd.Timestamp(manifest.date_range.start, tz="UTC")
    end = pd.Timestamp(manifest.date_range.end, tz="UTC") + pd.Timedelta(days=1)
    outside = int(((published < start) | (published >= end)).sum())
    if outside:
        findings.append(
            _error(
                "published_at_out_of_range",
                "articles",
                f"{outside} artikel di luar date_range {manifest.date_range.start}..{manifest.date_range.end}",
            )
        )

    duplicated_urls = int(frame["url_hash"].duplicated().sum())
    if duplicated_urls:
        findings.append(
            _error("url_hash_duplicate", "articles", f"{duplicated_urls} url_hash duplikat")
        )

    empty_source = int(frame["source_id"].isna().sum())
    if empty_source:
        findings.append(_error("source_missing", "articles", f"{empty_source} artikel tanpa source_id"))

    _check_syndication(frame, findings)


def _check_syndication(frame: pd.DataFrame, findings: List[Finding]) -> None:
    """
    Sindikasi yang tidak dilabeli tidak digabung, tetapi harus terlihat.

    Menggabungkan otomatis berarti engine memutuskan dua artikel adalah satu
    peristiwa; keputusan itu milik pipeline ingest. Yang bisa dilakukan engine
    adalah melaporkan polanya, supaya kolom `dedupe_group` tidak tinggal kosong
    tanpa ada yang sadar bahwa dukungan tepi sedang digandakan.
    """
    if "title" not in frame.columns or "published_at" not in frame.columns:
        return

    titles = frame["title"].astype("string").fillna("").str.strip().str.casefold()
    titles = titles.str.replace(r"\s+", " ", regex=True)
    days = pd.to_datetime(frame["published_at"], errors="coerce", utc=True).dt.date
    labeled = (
        frame["dedupe_group"]
        if "dedupe_group" in frame.columns
        else pd.Series([None] * len(frame), index=frame.index)
    )
    keys = pd.DataFrame(
        {"title": titles, "day": days, "source": frame["source_id"]},
        index=frame.index,
    )[labeled.isna()]

    suspects = 0
    for (title, _day), group in keys.groupby(["title", "day"], dropna=True):
        if not title or len(group) < SYNDICATION_MIN_COPIES:
            continue
        if group["source"].nunique() >= SYNDICATION_MIN_COPIES:
            suspects += 1
    if suspects:
        findings.append(
            _warn(
                "syndication_suspected",
                "articles",
                f"{suspects} kelompok judul sama di hari yang sama tanpa dedupe_group",
            )
        )


def _check_mentions(frame: pd.DataFrame, findings: List[Finding]) -> None:
    negative = int((frame["count"] <= 0).sum())
    if negative:
        findings.append(_error("mention_count_invalid", "mentions", f"{negative} baris count <= 0"))

    confidence = frame["confidence"].dropna()
    if not confidence.empty and ((confidence < 0) | (confidence > 1)).any():
        findings.append(
            _error("confidence_out_of_range", "mentions", "confidence harus di rentang 0..1")
        )


def _check_transmission(frame: pd.DataFrame, findings: List[Finding]) -> None:
    if frame.empty:
        findings.append(_warn("layer_empty", "transmission", "Layer ada tetapi tanpa baris"))
        return

    same = int((frame["src"] == frame["dst"]).sum())
    if same:
        findings.append(_error("self_loop", "transmission", f"{same} transmisi menunjuk diri sendiri"))

    bad_alpha = int(((frame["alpha"] < 0) | (frame["alpha"] > 1)).sum())
    if bad_alpha:
        findings.append(_error("alpha_out_of_range", "transmission", f"{bad_alpha} alpha di luar 0..1"))

    ci_bad = int(
        (
            (frame["alpha_ci_low"] > frame["alpha"])
            | (frame["alpha"] > frame["alpha_ci_high"])
        ).sum()
    )
    if ci_bad:
        findings.append(
            _error("alpha_ci_invalid", "transmission", f"{ci_bad} CI tidak mengapit alpha")
        )

    negative_lead = int((frame["lead_time_min"] < 0).sum())
    if negative_lead:
        findings.append(
            _error("lead_time_invalid", "transmission", f"{negative_lead} lead_time_min negatif")
        )

    empty_method = int(frame["method"].fillna("").str.strip().eq("").sum())
    if empty_method:
        findings.append(_error("method_missing", "transmission", f"{empty_method} baris tanpa method"))


def _check_sentiment(frame: pd.DataFrame, findings: List[Finding]) -> None:
    if frame.empty:
        findings.append(_warn("layer_empty", "sentiment", "Layer ada tetapi tanpa baris"))
        return

    total = frame[["pos", "neu", "neg"]].sum(axis=1)
    off = int((total - 100.0).abs().gt(SENTIMENT_SUM_TOLERANCE).sum())
    if off:
        findings.append(
            _error("sentiment_sum_invalid", "sentiment", f"{off} baris tidak berjumlah ~100")
        )

    negative = int((frame[["pos", "neu", "neg"]] < 0).any(axis=1).sum())
    if negative:
        findings.append(_error("sentiment_negative_value", "sentiment", f"{negative} baris bernilai negatif"))

    empty_method = int(frame["method"].fillna("").str.strip().eq("").sum())
    if empty_method:
        findings.append(_error("method_missing", "sentiment", f"{empty_method} baris tanpa method"))


def _check_domain(domain: Domain, entities: pd.DataFrame, manifest: Manifest, findings: List[Finding]) -> None:
    ids = _distinct(entities, "entity_id")
    # ego_id kosong berarti dataset tanpa pusat (mis. sebaran titik panas),
    # bukan pelanggaran: jaringan tetap sah tanpa simpul ego.
    ego_id = (domain.ego_id or "").strip()
    if ego_id and ego_id not in ids:
        findings.append(
            _error("ego_not_in_entities", "domain", f"ego_id '{ego_id}' tidak ada di entities")
        )

    types = _distinct(entities, "entity_type")
    unknown = types - set(domain.entity_types)
    if domain.entity_types and unknown:
        findings.append(
            _error("entity_type_unknown", "entities", f"tipe tidak terdaftar di domain: {sorted(unknown)}")
        )

    previous_end: Optional[int] = None
    for epoch in domain.epochs:
        if epoch.start_year > epoch.end_year:
            findings.append(
                _error("epoch_invalid", "domain", f"{epoch.id}: start_year > end_year")
            )
        if previous_end is not None and epoch.start_year <= previous_end:
            findings.append(_error("epoch_overlap", "domain", f"{epoch.id} tumpang tindih dengan epos sebelumnya"))
        previous_end = max(previous_end or epoch.end_year, epoch.end_year)

    for epoch in domain.epochs:
        if epoch.end_year < manifest.date_range.start.year or epoch.start_year > manifest.date_range.end.year:
            findings.append(
                _warn(
                    "epoch_outside_range",
                    "domain",
                    f"{epoch.id} ({epoch.start_year}-{epoch.end_year}) di luar date_range",
                )
            )


def _check_layers(
    manifest: Manifest, present: Dict[str, bool], findings: List[Finding]
) -> None:
    for layer in ("transmission", "sentiment"):
        status = manifest.layers.get(layer)
        if status is None:
            continue
        if status == "ready" and not present.get(layer):
            findings.append(
                _error(
                    "layer_status_mismatch",
                    layer,
                    "manifest menyatakan ready tetapi tabel tidak ada/kosong",
                )
            )
        if status == "awaiting_input" and present.get(layer):
            findings.append(
                _error(
                    "layer_status_mismatch",
                    layer,
                    "manifest menyatakan awaiting_input tetapi tabel berisi data",
                )
            )


def validate_bundle(path: Path | str) -> List[Finding]:
    """Validasi satu bundle. Kembalikan temuan; list kosong berarti patuh."""
    findings, _ = validate_and_read(path)
    return findings


def validate_and_read(
    path: Path | str,
) -> Tuple[List[Finding], Dict[str, pd.DataFrame]]:
    """
    Validasi sekaligus serahkan frame yang sudah dibaca validator.

    Validator memang harus membaca setiap tabel untuk memeriksa kunci, tipe
    kolom, dan foreign key. Mengembalikan frame itu membuat pemanggil seperti
    `load_bundle` tidak perlu membuka berkas yang sama untuk kedua kalinya.
    """
    root = Path(path)
    findings: List[Finding] = []

    manifest_payload = _read_json(root / schema.MANIFEST, "manifest", findings)
    domain_payload = _read_json(root / schema.DOMAIN, "domain", findings)
    if manifest_payload is None or domain_payload is None:
        return findings, {}

    try:
        manifest = Manifest(**manifest_payload)
    except ValidationError as exc:
        findings.append(_error("manifest_invalid", "manifest", str(exc).splitlines()[0]))
        return findings, {}

    try:
        domain = Domain(**domain_payload)
    except ValidationError as exc:
        findings.append(_error("domain_invalid", "domain", str(exc).splitlines()[0]))
        return findings, {}

    if manifest.contract_version.split(".")[0] != str(schema.CONTRACT_MAJOR):
        findings.append(
            _error(
                "contract_version_mismatch",
                "manifest",
                f"bundle {manifest.contract_version} tidak kompatibel dengan engine {schema.CONTRACT_VERSION}",
            )
        )

    frames: Dict[str, pd.DataFrame] = {}
    present: Dict[str, bool] = {}
    for table, (relative, required_schema, required) in schema.TABLES.items():
        target = root / relative
        if not required and not target.exists():
            present[table] = False
            continue
        frame = _read_table(target, table, required_schema, findings)
        if frame is None:
            present[table] = False
            continue
        present[table] = not frame.empty
        frames[table] = frame

        recorded_sha = manifest.file_sha256.get(relative)
        if recorded_sha is None:
            findings.append(_warn("sha256_missing", table, f"manifest.file_sha256 tidak memuat '{relative}'"))
        elif recorded_sha != _sha256(target):
            findings.append(_error("sha256_mismatch", table, f"isi {relative} tidak cocok dengan manifest"))

        _check_primary_key(frame, table, findings)
        _check_counts(frame, table, manifest, findings)

    if "articles" in frames:
        _check_articles(frames["articles"], manifest, findings)

    if "entities" in frames and "articles" in frames:
        # source_id adalah penerbit artikel, bukan aktor jaringan. Penerbit boleh
        # tidak terdaftar di entities; itu hanya informasi, bukan pelanggaran.
        unknown_sources = _distinct(frames["articles"], "source_id") - _distinct(
            frames["entities"], "entity_id"
        )
        if unknown_sources:
            findings.append(
                _warn(
                    "source_not_in_entities",
                    "articles",
                    f"{len(unknown_sources)} penerbit tidak terdaftar di entities: "
                    f"{sorted(unknown_sources)[:5]}",
                )
            )

    if "mentions" in frames:
        _check_mentions(frames["mentions"], findings)
        if "articles" in frames:
            _check_foreign_keys(
                frames["mentions"], "mentions", "article_id",
                _distinct(frames["articles"], "article_id"), "articles", findings,
            )
        if "entities" in frames:
            _check_foreign_keys(
                frames["mentions"], "mentions", "entity_id",
                _distinct(frames["entities"], "entity_id"), "entities", findings,
            )

    if "article_topics" in frames:
        if "articles" in frames:
            _check_foreign_keys(
                frames["article_topics"], "article_topics", "article_id",
                _distinct(frames["articles"], "article_id"), "articles", findings,
            )
        if "topics" in frames:
            _check_foreign_keys(
                frames["article_topics"], "article_topics", "topic_id",
                _distinct(frames["topics"], "topic_id"), "topics", findings,
            )

    if "transmission" in frames:
        _check_transmission(frames["transmission"], findings)
        if "entities" in frames:
            ids = _distinct(frames["entities"], "entity_id")
            _check_foreign_keys(frames["transmission"], "transmission", "src", ids, "entities", findings)
            _check_foreign_keys(frames["transmission"], "transmission", "dst", ids, "entities", findings)

    if "sentiment" in frames:
        _check_sentiment(frames["sentiment"], findings)
        if "entities" in frames:
            _check_foreign_keys(
                frames["sentiment"], "sentiment", "entity_id",
                _distinct(frames["entities"], "entity_id"), "entities", findings,
            )

    if "entities" in frames:
        _check_domain(domain, frames["entities"], manifest, findings)

    _check_layers(manifest, present, findings)
    return findings, frames

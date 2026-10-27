"""Pembacaan bundle parquet menjadi struktur in-memory."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Collection, Dict, List, Optional

import pandas as pd
import pyarrow.parquet as pq

from ..contract import schema
from ..contract.models import Domain, Manifest, Presentation
from ..contract.validate import Finding, validate_and_read


class BundleInvalid(RuntimeError):
    """Bundle tidak memenuhi kontrak; pesan memuat kode temuan."""

    def __init__(self, findings: List[Finding]):
        self.findings = [f for f in findings if f.level == "error"]
        detail = "; ".join(f"{f.table}:{f.code} {f.message}" for f in self.findings[:5])
        super().__init__(f"{len(self.findings)} pelanggaran kontrak: {detail}")


@dataclass(frozen=True)
class DataBundle:
    """Snapshot data yang siap dihitung. Tidak ada IO lagi setelah ini."""

    root: Path
    manifest: Manifest
    domain: Domain
    entities: pd.DataFrame
    articles: pd.DataFrame
    mentions: pd.DataFrame
    topics: pd.DataFrame
    article_topics: pd.DataFrame
    transmission: Optional[pd.DataFrame] = None
    sentiment: Optional[pd.DataFrame] = None

    @property
    def has_transmission(self) -> bool:
        return self.transmission is not None and not self.transmission.empty

    @property
    def has_sentiment(self) -> bool:
        return self.sentiment is not None and not self.sentiment.empty

    @property
    def presentation(self) -> Optional[Presentation]:
        """Metadata tampilan mentah; default netral diterapkan `resolve_presentation`."""
        return self.manifest.presentation

    def layer_status(self, layer: str) -> str:
        if layer == "transmission":
            return "ready" if self.has_transmission else "awaiting_input"
        if layer == "sentiment":
            return "ready" if self.has_sentiment else "awaiting_input"
        raise KeyError(layer)

    def subset(self, article_ids: Collection[str]) -> "DataBundle":
        """
        Salinan bundle yang hanya memuat artikel tertentu.

        Dipakai analisis berjendela (epos, rentang tahun, what-if). Denominator
        NPMI ikut mengecil karena `articles` juga disaring — itu yang membuat
        NPMI per epos sebanding dengan NPMI seluruh korpus, bukan digelembungkan
        oleh artikel di luar jendela.
        """
        keep = set(str(value) for value in article_ids)
        articles = self.articles[self.articles["article_id"].astype(str).isin(keep)]
        mentions = self.mentions[self.mentions["article_id"].astype(str).isin(keep)]
        article_topics = self.article_topics[
            self.article_topics["article_id"].astype(str).isin(keep)
        ]
        return replace(
            self,
            articles=articles.reset_index(drop=True),
            mentions=mentions.reset_index(drop=True),
            article_topics=article_topics.reset_index(drop=True),
        )

    def counts(self) -> Dict[str, int]:
        return {
            "entities": len(self.entities),
            "articles": len(self.articles),
            "mentions": len(self.mentions),
            "topics": len(self.topics),
            "article_topics": len(self.article_topics),
            "transmission": 0 if self.transmission is None else len(self.transmission),
            "sentiment": 0 if self.sentiment is None else len(self.sentiment),
        }


def _read_frames(root: Path) -> Dict[str, pd.DataFrame]:
    """Baca semua tabel sekali; hanya dipakai saat validasi dilewati."""
    frames: Dict[str, pd.DataFrame] = {}
    for table, (relative, _, required) in schema.TABLES.items():
        target = root / relative
        if not required and not target.exists():
            continue
        frames[table] = pq.read_table(target).to_pandas()
    return frames


def _present(
    frames: Dict[str, pd.DataFrame], table: str
) -> Optional[pd.DataFrame]:
    """Tabel opsional yang kosong atau tidak ada berarti lapisan belum tersedia."""
    frame = frames.get(table)
    return None if frame is None or frame.empty else frame


def load_bundle(path: Path | str, strict: bool = True) -> DataBundle:
    """
    Muat bundle; dengan `strict`, pelanggaran kontrak langsung menggagalkan load.

    Frame diambil dari validator, bukan dibaca ulang: validator sudah membuka
    setiap parquet untuk memeriksa skema dan foreign key, jadi pembacaan kedua
    hanya membuang waktu.
    """
    root = Path(path)
    if strict:
        findings, frames = validate_and_read(root)
        errors = [f for f in findings if f.level == "error"]
        if errors:
            raise BundleInvalid(findings)
    else:
        frames = _read_frames(root)

    manifest = Manifest(
        **json.loads((root / schema.MANIFEST).read_text(encoding="utf-8"))
    )
    domain = Domain(**json.loads((root / schema.DOMAIN).read_text(encoding="utf-8")))

    return DataBundle(
        root=root,
        manifest=manifest,
        domain=domain,
        entities=frames["entities"],
        articles=frames["articles"],
        mentions=frames["mentions"],
        topics=frames["topics"],
        article_topics=frames["article_topics"],
        transmission=_present(frames, "transmission"),
        sentiment=_present(frames, "sentiment"),
    )

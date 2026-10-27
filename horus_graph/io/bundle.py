"""Pembacaan bundle parquet menjadi struktur in-memory."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Collection, Dict, List, Optional

import pandas as pd
import pyarrow.parquet as pq

from ..contract import schema
from ..contract.models import Domain, Manifest
from ..contract.validate import Finding, validate_bundle


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


def _read_optional(root: Path, table: str) -> Optional[pd.DataFrame]:
    relative = schema.TABLES[table][0]
    path = root / relative
    if not path.exists():
        return None
    frame = pq.read_table(path).to_pandas()
    return frame if not frame.empty else None


def load_bundle(path: Path | str, strict: bool = True) -> DataBundle:
    """Muat bundle; dengan `strict`, pelanggaran kontrak langsung menggagalkan load."""
    root = Path(path)
    if strict:
        findings = validate_bundle(root)
        errors = [f for f in findings if f.level == "error"]
        if errors:
            raise BundleInvalid(findings)

    manifest = Manifest(
        **json.loads((root / schema.MANIFEST).read_text(encoding="utf-8"))
    )
    domain = Domain(**json.loads((root / schema.DOMAIN).read_text(encoding="utf-8")))

    frames = {}
    for table, (relative, _, _) in schema.TABLES.items():
        if schema.TABLES[table][2]:
            frames[table] = pq.read_table(root / relative).to_pandas()

    return DataBundle(
        root=root,
        manifest=manifest,
        domain=domain,
        entities=frames["entities"],
        articles=frames["articles"],
        mentions=frames["mentions"],
        topics=frames["topics"],
        article_topics=frames["article_topics"],
        transmission=_read_optional(root, "transmission"),
        sentiment=_read_optional(root, "sentiment"),
    )

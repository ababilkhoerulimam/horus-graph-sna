"""
Ekspor korpus lama (horus-agent) menjadi bundle kontrak v1.

Ini alat migrasi, bukan bagian engine. Ia membaca repo lain secara read-only
(SQLite FTS5 + `config/domain.yaml` + matcher yang sudah ada) lalu menulis
bundle parquet. Setelah pipeline Kaggle menghasilkan bundle sendiri, modul ini
bisa dihapus tanpa menyentuh engine.

Batas yang dijaga:
- Hanya artikel bertanggal di dalam rentang domain yang masuk (populasi sama
  dengan builder lama), supaya angka golden bisa dibandingkan.
- `published_at` ditulis sebagai tengah malam UTC karena korpus hanya menyimpan
  tanggal. Ini keterbatasan sumber, bukan pilihan desain.
- `mentions.count = 1` berarti "entitas muncul di dokumen ini"; matcher lama
  berbasis kehadiran, bukan jumlah kemunculan. `confidence` dikosongkan karena
  matcher tidak menghasilkannya.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from ..contract.models import Domain, Epoch
from ..io.writer import write_bundle
from .legacy_presentation import (
    extract_from_legacy_repo,
    load_presentation_file,
    split_payload,
)

MATCHER_VERSION = "entitymatcher-v1"
GENERATOR = "horus-agent/export-legacy"


@dataclass(frozen=True)
class LegacyContext:
    """Objek yang diambil dari repo lama; dipisah agar transform bisa diuji."""

    domain: Any
    reader: Any
    entity_matcher: Any
    topic_matcher: Any
    git_sha: Optional[str] = None


def _stable_id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _split_keywords(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(" OR ") if part.strip()]


def domain_from_legacy(domain: Any) -> Domain:
    return Domain(
        domain_id=domain.club_id,
        ego_id=domain.ego_id,
        label=domain.club_display,
        league=getattr(domain, "league", None),
        entity_types=sorted({entity.entity_type for entity in domain.entities}),
        epochs=[
            Epoch(id=epoch.id, label=epoch.name, start_year=epoch.start_year, end_year=epoch.end_year)
            for epoch in domain.epochs
        ],
        clusters=sorted({entity.cluster for entity in domain.entities}),
    )


def entities_frame(
    domain: Any, descriptions: Optional[Dict[str, str]] = None
) -> pd.DataFrame:
    """
    Tabel entitas termasuk kolom presentasi opsional (v1.1).

    `description` datang dari berkas presentasi; atribut tampilan lain sudah
    tersedia di `config/domain.yaml` lama.
    """
    descriptions = descriptions or {}
    return pd.DataFrame(
        {
            "entity_id": [entity.id for entity in domain.entities],
            "entity_type": [entity.entity_type for entity in domain.entities],
            "label": [entity.label for entity in domain.entities],
            "aliases": [list(entity.aliases) for entity in domain.entities],
            "first_seen": [None] * len(domain.entities),
            "description": [
                descriptions.get(entity.id) for entity in domain.entities
            ],
            "cluster": [getattr(entity, "cluster", None) for entity in domain.entities],
            "color": [getattr(entity, "color", None) for entity in domain.entities],
            "tier": [getattr(entity, "tier", None) for entity in domain.entities],
            "ring_level": [
                getattr(entity, "ring_level", None) for entity in domain.entities
            ],
            "sector": [getattr(entity, "sector", None) for entity in domain.entities],
            # Label selalu tampil untuk dua tingkat teratas; UI memakai `tier`
            # bila kolom ini kosong.
            "is_anchor": [
                _tier(entity) is not None and _tier(entity) <= 1
                for entity in domain.entities
            ],
        }
    )


def _tier(entity: Any) -> Optional[int]:
    value = getattr(entity, "tier", None)
    return int(value) if value is not None else None


def topics_frame(domain: Any) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "topic_id": [topic.id for topic in domain.topics],
            "label": [topic.label for topic in domain.topics],
            "keywords": [_split_keywords(topic.keywords) for topic in domain.topics],
        }
    )


def build_frames(
    articles: Iterable[Any],
    entity_matcher: Any,
    topic_matcher: Any,
    progress: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Ubah artikel + matcher menjadi tabel kontrak (tanpa menyentuh disk)."""
    article_rows: List[Dict[str, Any]] = []
    mention_rows: List[Dict[str, Any]] = []
    article_topic_rows: List[Dict[str, Any]] = []

    for index, article in enumerate(articles, start=1):
        if progress and index % 5000 == 0:
            print(f"  ... {index} artikel", file=sys.stderr)

        url = (article.url or "").strip()
        article_id = _stable_id("a", url) if url else _stable_id("a", f"row{article.row_id}")
        url_hash = hashlib.sha256((url or f"row{article.row_id}").encode("utf-8")).hexdigest()[:32]

        published = article.published_at
        article_rows.append(
            {
                "article_id": article_id,
                "source_id": article.site,
                "published_at": f"{published.isoformat()}T00:00:00Z" if published else None,
                "url_hash": url_hash,
                "title": (article.title or "").strip(),
                "lang": "id",
                "dedupe_group": None,
                "word_count": len((article.body or "").split()),
            }
        )

        for entity_id in sorted(entity_matcher.find(article.text, article.site)):
            mention_rows.append(
                {
                    "article_id": article_id,
                    "entity_id": entity_id,
                    "count": 1,
                    "confidence": None,
                    "matcher_version": MATCHER_VERSION,
                }
            )

        for topic_id in sorted(set(topic_matcher.classify(article.text))):
            article_topic_rows.append(
                {"article_id": article_id, "topic_id": topic_id, "score": None}
            )

    return {
        "articles": pd.DataFrame(article_rows),
        "mentions": pd.DataFrame(mention_rows),
        "article_topics": pd.DataFrame(article_topic_rows),
    }


def _legacy_context(repo: Path) -> LegacyContext:
    repo = repo.resolve()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from src.core.config import get_domain  # type: ignore[import-not-found]
    from src.core.corpus import CorpusReader  # type: ignore[import-not-found]
    from src.core.matching import EntityMatcher, TopicMatcher  # type: ignore[import-not-found]

    git_sha = None
    head = repo / ".git" / "HEAD"
    if head.exists():
        try:
            ref = head.read_text(encoding="utf-8").strip()
            if ref.startswith("ref:"):
                ref_path = repo / ".git" / ref.split(" ", 1)[1]
                git_sha = ref_path.read_text(encoding="utf-8").strip()[:12]
        except Exception:
            git_sha = None

    return LegacyContext(
        domain=get_domain(),
        reader=CorpusReader(),
        entity_matcher=EntityMatcher(),
        topic_matcher=TopicMatcher(),
        git_sha=git_sha,
    )


def export_legacy_bundle(
    repo: Path | str,
    out: Path | str,
    limit: Optional[int] = None,
    progress: bool = False,
    presentation: Optional[Path | str] = None,
    auto_presentation: bool = False,
) -> Dict[str, Any]:
    """
    Ekspor korpus repo lama ke bundle. `limit` hanya untuk uji cepat.

    Metadata tampilan diambil dari `presentation` (berkas JSON) atau, bila
    `auto_presentation`, diekstrak dari visualizer lama. Tanpa keduanya, bundle
    ditulis tanpa presentasi dan engine memakai default netral.
    """
    context = _legacy_context(Path(repo))
    domain = context.domain
    year_span = tuple(domain.year_span)

    payload: Dict[str, Any] = {}
    if presentation is not None:
        payload = load_presentation_file(presentation)
    elif auto_presentation:
        payload = extract_from_legacy_repo(Path(repo), domain)

    meta, descriptions = split_payload(payload) if payload else (None, {})

    iterator = context.reader.iter_articles(year_range=year_span, require_date=True)
    if limit:
        iterator = (article for index, article in enumerate(iterator) if index < limit)

    frames = build_frames(
        iterator, context.entity_matcher, context.topic_matcher, progress=progress
    )
    frames["entities"] = entities_frame(domain, descriptions)
    frames["topics"] = topics_frame(domain)

    extra: Dict[str, Any] = {
        "population": {"year_span": list(year_span), "require_date": True, "limit": limit}
    }
    if meta is not None:
        extra["presentation"] = meta

    manifest = write_bundle(
        out,
        frames=frames,
        domain=domain_from_legacy(domain),
        dataset_id=domain.club_id,
        date_range=(pd.Timestamp(f"{year_span[0]}-01-01").date(), pd.Timestamp(f"{year_span[1]}-12-31").date()),
        generator=GENERATOR,
        generator_version="1",
        generator_git_sha=context.git_sha,
        dictionary_version="domain.yaml@1",
        extra=extra,
    )
    return {
        "bundle": str(out),
        "counts": manifest.counts,
        "layers": manifest.layers,
        "presentation": meta is not None,
        "described_entities": len(descriptions),
    }

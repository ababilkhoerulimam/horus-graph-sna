"""Fixture bersama: bundle sintetis kecil, tanpa IO dan tanpa data nyata."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

import pandas as pd
import pytest

from horus_graph.contract.models import DateRange, Domain, Epoch, GeneratorInfo, Manifest
from horus_graph.io.bundle import DataBundle

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_BUNDLE = REPO_ROOT / "data" / "bundles" / "horus-agent-2026-10-27"


def _manifest(articles: int, entities: int, mentions: int) -> Manifest:
    return Manifest(
        contract_version="1.0.0",
        dataset_id="synthetic",
        snapshot_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        date_range=DateRange(start=date(2021, 1, 1), end=date(2026, 12, 31)),
        counts={"entities": entities, "articles": articles, "mentions": mentions},
        generator=GeneratorInfo(name="tests/synthetic", version="1"),
        layers={"transmission": "awaiting_input", "sentiment": "awaiting_input"},
    )


def build_bundle(
    entity_ids: Sequence[str],
    mentions: Iterable[Tuple[str, str, int]],
    articles: int,
    ego: str = "A",
    epochs: Sequence[Tuple[str, int, int]] = (),
    entity_types: Optional[Sequence[str]] = None,
    dates: Optional[Sequence[str]] = None,
    sources: Optional[Sequence[str]] = None,
    topics: Sequence[str] = (),
    article_topics: Iterable[Tuple[str, str]] = (),
    transmission: Optional[pd.DataFrame] = None,
    sentiment: Optional[pd.DataFrame] = None,
) -> DataBundle:
    """
    Bundle minimal yang memenuhi bentuk kontrak.

    `articles` adalah jumlah artikel di korpus (termasuk yang tidak menyebut
    entitas apa pun) karena angka itulah denominator NPMI. `dates` mengisi
    `published_at` per artikel (tanggal saja, presisi sumber).
    """
    entity_frame = pd.DataFrame(
        {
            "entity_id": list(entity_ids),
            "entity_type": list(entity_types) if entity_types else ["Entity"] * len(entity_ids),
            "label": list(entity_ids),
        }
    )
    published = list(dates) if dates else ["2024-01-01"] * articles
    if len(published) != articles:
        raise ValueError("dates harus sepanjang jumlah artikel")
    article_frame = pd.DataFrame(
        {
            "article_id": [f"art{i:03d}" for i in range(articles)],
            "source_id": list(sources) if sources else ["src"] * articles,
            "published_at": [f"{value}T00:00:00Z" for value in published],
            "url_hash": [f"hash{i:03d}" for i in range(articles)],
        }
    )
    mention_frame = pd.DataFrame(
        list(mentions), columns=["article_id", "entity_id", "count"]
    )
    if not mention_frame.empty:
        mention_frame["matcher_version"] = "test-v1"

    domain = Domain(
        domain_id="synthetic",
        ego_id=ego,
        label="Synthetic",
        entity_types=list(entity_types) if entity_types else ["Entity"],
        epochs=[
            Epoch(id=epoch_id, label=epoch_id, start_year=start, end_year=end)
            for epoch_id, start, end in epochs
        ],
    )
    return DataBundle(
        root=REPO_ROOT,
        manifest=_manifest(len(article_frame), len(entity_frame), len(mention_frame)),
        domain=domain,
        entities=entity_frame,
        articles=article_frame,
        mentions=mention_frame,
        topics=pd.DataFrame(
            {"topic_id": list(topics), "label": list(topics)}
        ),
        article_topics=pd.DataFrame(
            list(article_topics), columns=["article_id", "topic_id"]
        ),
        transmission=transmission,
        sentiment=sentiment,
    )


@pytest.fixture
def bundle_factory():
    return build_bundle


@pytest.fixture(scope="session")
def golden_bundle() -> DataBundle:
    if not GOLDEN_BUNDLE.exists():
        pytest.skip(f"bundle golden tidak ada: {GOLDEN_BUNDLE}")
    from horus_graph.io.bundle import load_bundle

    return load_bundle(GOLDEN_BUNDLE)

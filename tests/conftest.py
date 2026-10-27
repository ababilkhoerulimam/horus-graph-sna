"""Fixture bersama: bundle sintetis kecil, tanpa IO dan tanpa data nyata."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import pandas as pd
import pytest

from horus_graph.contract.models import DateRange, Domain, GeneratorInfo, Manifest
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
) -> DataBundle:
    """
    Bundle minimal yang memenuhi bentuk kontrak.

    `articles` adalah jumlah artikel di korpus (termasuk yang tidak menyebut
    entitas apa pun) karena angka itulah denominator NPMI.
    """
    entity_frame = pd.DataFrame(
        {
            "entity_id": list(entity_ids),
            "entity_type": ["Entity"] * len(entity_ids),
            "label": list(entity_ids),
        }
    )
    article_frame = pd.DataFrame(
        {
            "article_id": [f"art{i:03d}" for i in range(articles)],
            "source_id": ["src"] * articles,
            "published_at": ["2024-01-01T00:00:00Z"] * articles,
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
        entity_types=["Entity"],
    )
    return DataBundle(
        root=REPO_ROOT,
        manifest=_manifest(len(article_frame), len(entity_frame), len(mention_frame)),
        domain=domain,
        entities=entity_frame,
        articles=article_frame,
        mentions=mention_frame,
        topics=pd.DataFrame(columns=["topic_id", "label"]),
        article_topics=pd.DataFrame(columns=["article_id", "topic_id"]),
        transmission=None,
        sentiment=None,
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

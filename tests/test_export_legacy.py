"""Transformasi artikel lama menjadi tabel kontrak (tanpa SQLite)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import pandas as pd

from horus_graph.contract import validate_bundle
from horus_graph.export.legacy import build_frames
from horus_graph.io import write_bundle


@dataclass(frozen=True)
class FakeArticle:
    row_id: int
    title: str
    body: str
    site: str
    published_at: Optional[date]
    url: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"


class FakeEntityMatcher:
    def __init__(self, mapping: dict[str, set[str]]):
        self.mapping = mapping

    def find(self, text: str, site: str) -> set[str]:
        return self.mapping.get(text.split("\n")[0], set())


class FakeTopicMatcher:
    def __init__(self, mapping: dict[str, list[str]]):
        self.mapping = mapping

    def classify(self, text: str) -> List[str]:
        return self.mapping.get(text.split("\n")[0], [])


ARTICLES = [
    FakeArticle(1, "Ego menang", "Ego FC menang.", "media-x", date(2021, 3, 1), "https://x/1"),
    FakeArticle(2, "Transfer", "Person A pindah.", "media-x", date(2023, 7, 15), "https://x/2"),
]


def _frames():
    return build_frames(
        ARTICLES,
        FakeEntityMatcher({"Ego menang": {"Ego FC"}, "Transfer": {"Ego FC", "Person A"}}),
        FakeTopicMatcher({"Ego menang": ["taktik"], "Transfer": ["transfer"]}),
    )


def test_build_frames_membentuk_tabel_kontrak():
    frames = _frames()
    assert set(frames) == {"articles", "mentions", "article_topics"}
    assert len(frames["articles"]) == 2
    assert len(frames["mentions"]) == 3
    assert len(frames["article_topics"]) == 2

    articles = frames["articles"]
    assert articles["published_at"].tolist() == [
        "2021-03-01T00:00:00Z",
        "2023-07-15T00:00:00Z",
    ]
    assert articles["url_hash"].is_unique
    assert articles["article_id"].is_unique


def test_mention_dan_topic_menunjuk_article_id_yang_sama():
    frames = _frames()
    ids = set(frames["articles"]["article_id"])
    assert set(frames["mentions"]["article_id"]) <= ids
    assert set(frames["article_topics"]["article_id"]) <= ids


def test_url_sama_menghasilkan_article_id_sama():
    first = build_frames([ARTICLES[0]], FakeEntityMatcher({}), FakeTopicMatcher({}))
    second = build_frames(
        [FakeArticle(99, "Ego menang", "Ego FC menang.", "media-x", date(2021, 3, 1), "https://x/1")],
        FakeEntityMatcher({}),
        FakeTopicMatcher({}),
    )
    assert first["articles"]["article_id"].iloc[0] == second["articles"]["article_id"].iloc[0]


def test_bundle_hasil_transform_lolos_validator(tmp_path):
    frames = _frames()
    frames["entities"] = pd.DataFrame(
        {
            "entity_id": ["Ego FC", "Person A"],
            "entity_type": ["Organization", "Person"],
            "label": ["Ego FC", "Person A"],
            "aliases": [[], []],
            "first_seen": [None, None],
        }
    )
    frames["topics"] = pd.DataFrame(
        {"topic_id": ["taktik", "transfer"], "label": ["Taktik", "Transfer"], "keywords": [[], []]}
    )

    from horus_graph.contract import Domain, Epoch

    write_bundle(
        tmp_path / "bundle",
        frames=frames,
        domain=Domain(
            domain_id="uji",
            ego_id="Ego FC",
            label="Ego FC",
            entity_types=["Organization", "Person"],
            epochs=[Epoch(id="epoch_1", label="Awal", start_year=2021, end_year=2026)],
        ),
        dataset_id="uji",
        date_range=(date(2021, 1, 1), date(2026, 12, 31)),
        generator="pytest",
    )
    findings = validate_bundle(tmp_path / "bundle")
    assert [f for f in findings if f.level == "error"] == []

"""
Jaringan bipartit topik-aktor.

Sisi aktor dihitung dari `mentions`, sisi topik dari `article_topics`; edge
adalah artikel yang memuat keduanya. Entitas bertipe media dikecualikan dari
sisi aktor: portal yang meliput hampir semua topik akan terlihat sebagai aktor
paling "khas" di setiap topik, padahal itu artefak cakupan, bukan kedekatan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

from ..io.bundle import DataBundle
from . import association

DEFAULT_EXCLUDED_TYPES: Tuple[str, ...] = ("Source",)


@dataclass(frozen=True)
class TopicActorBundle:
    """Dua sisi + edge berbobot NPMI, semuanya dari satu populasi artikel."""

    topics: pd.DataFrame
    actors: pd.DataFrame
    edges: pd.DataFrame
    membership: Mapping[str, Tuple[str, ...]]
    total_articles: int

    def summary(self) -> Dict[str, object]:
        values = self.edges["npmi"].to_numpy(dtype=float) if not self.edges.empty else np.zeros(0)
        return {
            "topics": int(len(self.topics)),
            "actors": int(len(self.actors)),
            "edges": int(len(self.edges)),
            "negative_edges": int((values < 0).sum()),
            "npmi_min": None if values.size == 0 else round(float(values.min()), 4),
            "npmi_max": None if values.size == 0 else round(float(values.max()), 4),
            "articles": self.total_articles,
        }


def build_bipartite(
    bundle: DataBundle,
    min_support: int = 3,
    exclude_entity_types: Sequence[str] = DEFAULT_EXCLUDED_TYPES,
    membership_top_n: int = 20,
    membership_min_npmi: float = 0.0,
) -> TopicActorBundle:
    """Hitung n_t, n_a, n_ta, n_media-topic lalu NPMI untuk setiap edge."""
    total = max(len(bundle.articles), 1)
    excluded = set(str(value) for value in exclude_entity_types)
    excluded_ids = set(
        bundle.entities.loc[
            bundle.entities["entity_type"].astype(str).isin(excluded), "entity_id"
        ].astype(str)
    )

    mentions = bundle.mentions[["article_id", "entity_id"]].astype(str).drop_duplicates()
    article_topics = (
        bundle.article_topics[["article_id", "topic_id"]].astype(str).drop_duplicates()
    )

    n_t = article_topics.groupby("topic_id")["article_id"].nunique()
    n_a = mentions.groupby("entity_id")["article_id"].nunique()

    joined = article_topics.merge(mentions, on="article_id", how="inner")
    if excluded_ids:
        joined = joined[~joined["entity_id"].isin(excluded_ids)]
    n_ta = joined.groupby(["topic_id", "entity_id"])["article_id"].nunique()
    n_ta = n_ta[n_ta >= min_support]

    topics = _topic_table(bundle, n_t)
    actors = _actor_table(bundle, n_a, excluded_ids)

    edges = _edge_table(n_ta, n_t, n_a, total)
    membership = _membership(edges, membership_top_n, membership_min_npmi)
    return TopicActorBundle(
        topics=topics,
        actors=actors,
        edges=edges,
        membership=membership,
        total_articles=total,
    )


def _topic_table(bundle: DataBundle, n_t: pd.Series) -> pd.DataFrame:
    frame = bundle.topics.copy()
    frame["topic_id"] = frame["topic_id"].astype(str)
    frame["articles"] = frame["topic_id"].map(n_t).fillna(0).astype(int)
    return frame[["topic_id", "label", "articles"]].sort_values(
        "articles", ascending=False, ignore_index=True
    )


def _actor_table(
    bundle: DataBundle, n_a: pd.Series, excluded_ids: set
) -> pd.DataFrame:
    frame = bundle.entities[["entity_id", "entity_type", "label"]].copy()
    frame["entity_id"] = frame["entity_id"].astype(str)
    frame = frame[~frame["entity_id"].isin(excluded_ids)]
    frame["articles"] = frame["entity_id"].map(n_a).fillna(0).astype(int)
    frame = frame[frame["articles"] > 0]
    return frame.sort_values(
        ["articles", "entity_id"], ascending=[False, True], ignore_index=True
    )


def _edge_table(
    n_ta: pd.Series, n_t: pd.Series, n_a: pd.Series, total: int
) -> pd.DataFrame:
    if n_ta.empty:
        return pd.DataFrame(
            columns=["topic_id", "entity_id", "support", "npmi", "topic_articles", "actor_articles"]
        )
    frame = n_ta.rename("support").reset_index()
    frame["topic_articles"] = frame["topic_id"].map(n_t).fillna(0).astype(int)
    frame["actor_articles"] = frame["entity_id"].map(n_a).fillna(0).astype(int)
    frame["npmi"] = association.npmi_array(
        frame["support"].to_numpy(),
        frame["topic_articles"].to_numpy(),
        frame["actor_articles"].to_numpy(),
        total,
    )
    frame = frame[np.isfinite(frame["npmi"].to_numpy(dtype=float))]
    frame["npmi"] = frame["npmi"].round(4)
    return frame.sort_values(
        ["topic_id", "npmi", "entity_id"],
        ascending=[True, False, True],
        ignore_index=True,
    )[["topic_id", "entity_id", "support", "npmi", "topic_articles", "actor_articles"]]


def _membership(
    edges: pd.DataFrame, top_n: int, min_npmi: float
) -> Dict[str, Tuple[str, ...]]:
    """
    Keanggotaan topik = aktor paling khas (NPMI tertinggi), bukan sekadar hadir.

    Tanpa batas ini topik luas seperti "Liputan Umum" akan memuat semua aktor
    dan tidak lagi membedakan apa pun.
    """
    if edges.empty:
        return {}
    filtered = edges[edges["npmi"] >= min_npmi]
    grouped: Dict[str, Tuple[str, ...]] = {}
    for topic_id, block in filtered.groupby("topic_id", sort=True):
        ordered = block.sort_values(
            ["npmi", "support", "entity_id"], ascending=[False, False, True]
        )
        grouped[str(topic_id)] = tuple(ordered["entity_id"].head(top_n).astype(str))
    return grouped

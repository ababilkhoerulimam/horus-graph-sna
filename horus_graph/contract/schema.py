"""
Skema parquet kontrak bundle v1.

Skema di sini adalah satu-satunya definisi bentuk data yang diterima engine.
Kolom tambahan diizinkan (pipeline boleh membawa metadata ekstra), kolom wajib
yang hilang ditolak. Tipe diperiksa longgar untuk numerik (int/float saling
menerima) karena pipeline di Kaggle sering menulis int32 vs int64.
"""

from __future__ import annotations

import pyarrow as pa

CONTRACT_VERSION = "1.2.0"
CONTRACT_MAJOR = 1

ENTITIES = pa.schema(
    [
        pa.field("entity_id", pa.string(), nullable=False),
        pa.field("entity_type", pa.string(), nullable=False),
        pa.field("label", pa.string(), nullable=False),
        pa.field("aliases", pa.list_(pa.string()), nullable=True),
        pa.field("first_seen", pa.string(), nullable=True),
    ]
)

# Kolom presentasi (v1.1). Semuanya opsional: bundle 1.0 tetap sah, dan engine
# memakai default netral bila kolomnya tidak ada. Dipisahkan dari ENTITIES
# supaya `missing_columns()` tidak pernah menuntutnya.
ENTITIES_OPTIONAL = pa.schema(
    [
        pa.field("description", pa.string(), nullable=True),
        pa.field("cluster", pa.string(), nullable=True),
        pa.field("color", pa.string(), nullable=True),
        pa.field("tier", pa.int64(), nullable=True),
        pa.field("ring_level", pa.int64(), nullable=True),
        pa.field("sector", pa.string(), nullable=True),
        pa.field("is_anchor", pa.bool_(), nullable=True),
    ]
)

# Tautan sumber artikel: dibutuhkan panel bukti agar temuan bisa dibuka,
# tetapi tidak dipakai perhitungan apa pun.
ARTICLES_OPTIONAL = pa.schema(
    [pa.field("url", pa.string(), nullable=True)]
)

OPTIONAL_COLUMNS = {"entities": ENTITIES_OPTIONAL, "articles": ARTICLES_OPTIONAL}

ARTICLES = pa.schema(
    [
        pa.field("article_id", pa.string(), nullable=False),
        pa.field("source_id", pa.string(), nullable=False),
        pa.field("published_at", pa.string(), nullable=False),
        pa.field("url_hash", pa.string(), nullable=False),
        pa.field("title", pa.string(), nullable=True),
        pa.field("lang", pa.string(), nullable=True),
        pa.field("dedupe_group", pa.string(), nullable=True),
        pa.field("word_count", pa.int64(), nullable=True),
    ]
)

MENTIONS = pa.schema(
    [
        pa.field("article_id", pa.string(), nullable=False),
        pa.field("entity_id", pa.string(), nullable=False),
        pa.field("count", pa.int64(), nullable=False),
        pa.field("confidence", pa.float64(), nullable=True),
        pa.field("matcher_version", pa.string(), nullable=False),
    ]
)

TOPICS = pa.schema(
    [
        pa.field("topic_id", pa.string(), nullable=False),
        pa.field("label", pa.string(), nullable=False),
        pa.field("keywords", pa.list_(pa.string()), nullable=True),
    ]
)

ARTICLE_TOPICS = pa.schema(
    [
        pa.field("article_id", pa.string(), nullable=False),
        pa.field("topic_id", pa.string(), nullable=False),
        pa.field("score", pa.float64(), nullable=True),
    ]
)

TRANSMISSION = pa.schema(
    [
        pa.field("src", pa.string(), nullable=False),
        pa.field("dst", pa.string(), nullable=False),
        pa.field("alpha", pa.float64(), nullable=False),
        pa.field("alpha_ci_low", pa.float64(), nullable=False),
        pa.field("alpha_ci_high", pa.float64(), nullable=False),
        pa.field("lead_time_min", pa.float64(), nullable=False),
        pa.field("method", pa.string(), nullable=False),
        pa.field("n_events", pa.int64(), nullable=True),
        pa.field("window_start", pa.string(), nullable=True),
        pa.field("window_end", pa.string(), nullable=True),
    ]
)

SENTIMENT = pa.schema(
    [
        pa.field("entity_id", pa.string(), nullable=False),
        pa.field("pos", pa.float64(), nullable=False),
        pa.field("neu", pa.float64(), nullable=False),
        pa.field("neg", pa.float64(), nullable=False),
        pa.field("method", pa.string(), nullable=False),
        pa.field("confidence", pa.float64(), nullable=True),
        pa.field("window_start", pa.string(), nullable=True),
        pa.field("window_end", pa.string(), nullable=True),
    ]
)

# Nama tabel -> (path relatif, skema, wajib?)
TABLES = {
    "entities": ("entities.parquet", ENTITIES, True),
    "articles": ("articles.parquet", ARTICLES, True),
    "mentions": ("mentions.parquet", MENTIONS, True),
    "topics": ("topics.parquet", TOPICS, True),
    "article_topics": ("article_topics.parquet", ARTICLE_TOPICS, True),
    "transmission": ("layers/transmission.parquet", TRANSMISSION, False),
    "sentiment": ("layers/sentiment.parquet", SENTIMENT, False),
}

PRIMARY_KEYS = {
    "entities": ["entity_id"],
    "articles": ["article_id"],
    "mentions": ["article_id", "entity_id"],
    "topics": ["topic_id"],
    "article_topics": ["article_id", "topic_id"],
    "transmission": ["src", "dst"],
    "sentiment": ["entity_id"],
}

MANIFEST = "manifest.json"
DOMAIN = "domain.json"


def missing_columns(schema: pa.Schema, required: pa.Schema) -> list[str]:
    """Kolom wajib yang tidak ada di skema aktual."""
    present = set(schema.names)
    return [field.name for field in required if field.name not in present]

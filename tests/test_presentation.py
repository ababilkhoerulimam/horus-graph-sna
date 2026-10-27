"""
Metadata presentasi: default harus netral, dan yang datang dari bundle menang.

Aturan yang dijaga di sini: repo ini tidak boleh tahu domain apa pun. Kalau
suatu saat default memuat nama klub, liga, atau kota, test ini gagal.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa

from horus_graph.contract import schema
from horus_graph.contract.models import (
    ActionRule,
    ClusterStyle,
    EgoStyle,
    EntityTypeStyle,
    Palette,
    Presentation as PresentationMeta,
    RadiusScale,
)
from horus_graph.io import load_bundle, write_bundle
from horus_graph.presentation import resolve_presentation


def _rows():
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 14) for e in ("B", "C")]
    return rows


def _with_meta(bundle, meta: PresentationMeta):
    return replace(
        bundle, manifest=bundle.manifest.model_copy(update={"presentation": meta})
    )


def test_default_netral_tanpa_presentation(bundle_factory):
    presentation = resolve_presentation(
        bundle_factory(["A", "B", "C"], _rows(), articles=40, ego="A")
    )

    assert presentation.title == "synthetic"  # jatuh ke dataset_id, bukan nama domain
    assert presentation.subtitle is None
    assert presentation.ego is not None and presentation.ego.id == "A"
    assert set(presentation.entity_types) == {"Entity"}
    assert presentation.label("node") == "Simpul"
    assert presentation.text("no_bundle").startswith("Belum ada bundle")


def test_default_tidak_memuat_nama_domain(bundle_factory):
    payload = resolve_presentation(
        bundle_factory(["A", "B", "C"], _rows(), articles=40)
    ).as_dict()
    text = json.dumps(payload, ensure_ascii=False).lower()

    for word in ("dewa", "liga", "sepak bola", "klub", "football"):
        assert word not in text


def test_ego_kosong_berarti_tanpa_pusat(bundle_factory):
    presentation = resolve_presentation(
        bundle_factory(["A", "B", "C"], _rows(), articles=40, ego="")
    )

    assert presentation.ego is None
    assert presentation.as_dict()["ego"] is None


def test_ego_dari_presentation_menimpa_domain(bundle_factory):
    bundle = _with_meta(
        bundle_factory(["A", "B", "C"], _rows(), articles=40, ego="A"),
        PresentationMeta(ego=EgoStyle(id="B")),
    )
    presentation = resolve_presentation(bundle)

    assert presentation.ego.id == "B"
    # label kosong diisi dari tabel entities, bukan dibiarkan None
    assert presentation.ego.label == "B"


def test_presentation_bundle_menimpa_seluruh_default(bundle_factory):
    meta = PresentationMeta(
        title="Analisis Kebakaran Lahan",
        subtitle="2021-2024",
        entity_types=[
            EntityTypeStyle(id="Entity", label="Aktor", color="#123456"),
            EntityTypeStyle(id="Lokasi", label="Wilayah"),
        ],
        clusters=[ClusterStyle(id="C1", label="Zona Barat", color="#654321")],
        palette=Palette(community=["#111111", "#222222"]),
        orbit_tiers=["PUSAT", "LUAR"],
        epoch_narratives={"2021": "Musim kering panjang."},
        labels={"node": "Aktor"},
        wording={"empty_anomaly": "Tidak ada lonjakan."},
        action_rules={"broker": ActionRule(title="Jembatan", body="{label} menghubungkan")},
        sankey_columns=["Sumber", "Isu", "Aktor"],
        radius_scale=RadiusScale(min=8, max=40),
    )
    presentation = resolve_presentation(
        _with_meta(bundle_factory(["A", "B", "C"], _rows(), articles=40, ego=""), meta)
    )

    assert presentation.title == "Analisis Kebakaran Lahan"
    assert presentation.subtitle == "2021-2024"
    assert presentation.ego is None
    assert presentation.entity_type("Entity").label == "Aktor"
    assert presentation.color_for("Entity") == "#123456"
    # tipe tanpa warna memakai palet bundle secara bergilir
    assert presentation.color_for("Lokasi", index=1) == "#222222"
    assert presentation.clusters["C1"].label == "Zona Barat"
    assert presentation.orbit_tiers == ("PUSAT", "LUAR")
    assert presentation.epoch_narratives["2021"] == "Musim kering panjang."
    assert presentation.label("node") == "Aktor"
    assert presentation.label("edge") == "Sisi"  # default yang tidak ditimpa tetap ada
    assert presentation.text("empty_anomaly") == "Tidak ada lonjakan."
    assert presentation.action_rules["broker"].title == "Jembatan"
    assert presentation.sankey_columns == ("Sumber", "Isu", "Aktor")
    assert presentation.radius_scale.max == 40.0


def test_tipe_entitas_diturunkan_dari_tabel_bila_tidak_dideklarasikan(bundle_factory):
    bundle = bundle_factory(
        ["A", "B", "C"],
        _rows(),
        articles=40,
        entity_types=["Person", "Person", "Organization"],
    )
    presentation = resolve_presentation(bundle)

    assert list(presentation.entity_types) == ["Person", "Organization"]
    assert presentation.entity_types["Person"].color is not None


def _pad(frame: pd.DataFrame, target: pa.Schema) -> pd.DataFrame:
    padded = frame.copy()
    for field in target:
        if field.name not in padded.columns:
            padded[field.name] = None
    return padded


def test_kolom_opsional_dan_presentation_bertahan_setelah_ditulis(tmp_path, bundle_factory):
    bundle = bundle_factory(["A", "B", "C"], _rows(), articles=40, ego="A")
    entities = _pad(bundle.entities, schema.ENTITIES)
    entities["description"] = ["Pusat", "Perantara", None]
    entities["cluster"] = ["C1", "C1", "C2"]
    entities["color"] = ["#000001", None, None]
    entities["tier"] = [0, 1, None]
    entities["ring_level"] = [0, 1, 2]
    entities["sector"] = ["center", None, "north"]
    entities["is_anchor"] = [True, False, None]

    meta = PresentationMeta(title="Judul Uji", ego=EgoStyle(id="A", label="Pusat"))

    root = tmp_path / "bundle"
    write_bundle(
        root,
        frames={
            "entities": entities,
            "articles": _pad(bundle.articles, schema.ARTICLES),
            "mentions": _pad(bundle.mentions, schema.MENTIONS),
            "topics": _pad(bundle.topics, schema.TOPICS),
            "article_topics": _pad(bundle.article_topics, schema.ARTICLE_TOPICS),
        },
        domain=bundle.domain,
        dataset_id="synthetic",
        date_range=(date(2021, 1, 1), date(2026, 12, 31)),
        generator="tests/presentation",
        extra={"presentation": meta},
    )

    loaded = load_bundle(root)  # memvalidasi ulang
    assert loaded.manifest.contract_version == schema.CONTRACT_VERSION
    assert loaded.presentation.title == "Judul Uji"
    assert set(schema.ENTITIES_OPTIONAL.names).issubset(loaded.entities.columns)
    assert loaded.entities.loc[0, "description"] == "Pusat"
    assert loaded.entities.loc[0, "tier"] == 0
    assert loaded.entities.loc[0, "is_anchor"] in (True, 1)

    presentation = resolve_presentation(loaded)
    assert presentation.title == "Judul Uji"
    assert presentation.ego.label == "Pusat"
    assert set(presentation.clusters) == {"C1", "C2"}


def test_bundle_lama_tanpa_kolom_opsional_tetap_sah(bundle_factory, tmp_path):
    """Bundle 1.0 (tanpa kolom presentasi) harus lolos validasi tanpa perubahan."""
    bundle = bundle_factory(["A", "B", "C"], _rows(), articles=40, ego="A")
    root = tmp_path / "bundle"
    write_bundle(
        root,
        frames={
            "entities": _pad(bundle.entities, schema.ENTITIES),
            "articles": _pad(bundle.articles, schema.ARTICLES),
            "mentions": _pad(bundle.mentions, schema.MENTIONS),
            "topics": _pad(bundle.topics, schema.TOPICS),
            "article_topics": _pad(bundle.article_topics, schema.ARTICLE_TOPICS),
        },
        domain=bundle.domain,
        dataset_id="synthetic",
        date_range=(date(2021, 1, 1), date(2026, 12, 31)),
        generator="tests/presentation",
    )

    loaded = load_bundle(root)
    assert "description" not in loaded.entities.columns
    assert loaded.presentation is None
    assert resolve_presentation(loaded).title == "synthetic"

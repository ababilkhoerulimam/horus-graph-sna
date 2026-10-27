"""API HTTP: setiap endpoint diuji pada bundle sintetis, bukan data nyata."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import time

import pandas as pd
import pyarrow as pa
import pytest

from horus_graph.api.app import create_app
from horus_graph.contract import schema
from horus_graph.io import write_bundle

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _pad(frame: pd.DataFrame, target: pa.Schema) -> pd.DataFrame:
    padded = frame.copy()
    for field in target:
        if field.name not in padded.columns:
            padded[field.name] = None
    return padded


def _write_bundle(
    root: Path, bundle_factory, sentiment: pd.DataFrame | None = None
) -> Path:
    """
    Rantai A-B-C-D di atas 80 artikel.

    Rantai murni membuat pasangan tengah (B-C) berasosiasi *negatif*: B dan C
    masing-masing muncul di separuh korpus, sementara kebersamaannya hanya
    seperempat. Menambah artikel latar tanpa entitas menurunkan marginal
    sehingga asosiasi ketiga pasangan kembali positif — sama seperti korpus
    nyata yang selalu punya artikel di luar topik.

    `sentiment` menulis `layers/sentiment.parquet`; tanpa itu lapisan sentimen
    berstatus `awaiting_input` dan simpul tidak boleh membawa blok sentimen.
    """
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 10) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(10, 20) for e in ("B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(20, 30) for e in ("C", "D")]
    dates = ["2021-06-01"] * 40 + ["2023-06-01"] * 40
    bundle = bundle_factory(
        ["A", "B", "C", "D"],
        rows,
        articles=80,
        ego="A",
        dates=dates,
        epochs=[("e1", 2021, 2022), ("e2", 2023, 2024)],
        topics=["T1"],
        article_topics=[(f"art{i:03d}", "T1") for i in range(0, 20)],
        sentiment=sentiment,
    )

    entities = _pad(bundle.entities, schema.ENTITIES)
    entities["description"] = ["Pusat", None, None, None]
    entities["ring_level"] = [0, 1, 2, 3]
    entities["is_anchor"] = [True, False, False, False]

    articles = _pad(bundle.articles, schema.ARTICLES)
    articles["url"] = [f"https://example.test/{index}" for index in range(len(articles))]

    frames = {
        "entities": entities,
        "articles": articles,
        "mentions": _pad(bundle.mentions, schema.MENTIONS),
        "topics": _pad(bundle.topics, schema.TOPICS),
        "article_topics": _pad(bundle.article_topics, schema.ARTICLE_TOPICS),
    }
    if sentiment is not None:
        frames["sentiment"] = _pad(sentiment, schema.SENTIMENT)

    write_bundle(
        root,
        frames=frames,
        domain=bundle.domain,
        dataset_id="synthetic",
        date_range=(date(2021, 1, 1), date(2026, 12, 31)),
        generator="tests/api",
    )
    return root


@pytest.fixture()
def client(tmp_path, bundle_factory) -> TestClient:
    root = _write_bundle(tmp_path / "bundle", bundle_factory)
    return TestClient(create_app(root))


@pytest.fixture()
def client_with_sentiment(tmp_path, bundle_factory) -> TestClient:
    frame = pd.DataFrame(
        {
            "entity_id": ["A", "B", "C", "D"],
            "pos": [60.0, 10.0, 25.0, 40.0],
            "neu": [30.0, 20.0, 25.0, 40.0],
            "neg": [10.0, 70.0, 50.0, 20.0],
            "method": ["inset"] * 4,
            "confidence": [0.9, 0.8, None, 0.7],
            "window_start": ["2021-01-01"] * 4,
            "window_end": ["2026-12-31"] * 4,
        }
    )
    root = _write_bundle(tmp_path / "bundle-sentiment", bundle_factory, sentiment=frame)
    return TestClient(create_app(root))


def test_health_menyebut_populasi(client):
    payload = client.get("/api/health").json()

    assert payload["status"] == "ok"
    assert payload["nodes"] == 4
    assert payload["contract_version"] == schema.CONTRACT_VERSION


def test_bootstrap_memuat_semua_kunci_yang_dipakai_ui(client):
    payload = client.get("/api/bootstrap").json()

    assert set(payload) == {
        "presentation",
        "dataset",
        "graph",
        "epochs",
        "topics",
        "entity_index",
        "coverage",
        "anomaly",
        "provenance",
    }
    assert len(payload["graph"]["nodes"]) == 4
    assert len(payload["graph"]["links"]) == 3
    assert payload["presentation"]["title"] == "synthetic"
    assert payload["entity_index"][0]["id"]


def test_simpul_membawa_presentasi_dari_bundle(client):
    nodes = {node["id"]: node for node in client.get("/api/bootstrap").json()["graph"]["nodes"]}

    assert nodes["A"]["is_ego"] is True
    assert nodes["A"]["description"] == "Pusat"
    assert nodes["A"]["orbit_label"] == "Pusat"
    assert nodes["B"]["orbit_label"] == "Cincin 1"
    assert nodes["A"]["is_anchor"] is True


def test_edge_membawa_npmi_dan_jaccard(client):
    links = client.get("/api/bootstrap").json()["graph"]["links"]

    for link in links:
        assert 0 <= link["jaccard"] <= 1
        assert link["salton_cosine"] is not None
        assert link["weight"] > 0


def test_tanpa_lapisan_sentimen_simpul_tidak_membawa_blok(client):
    payload = client.get("/api/bootstrap").json()

    assert payload["dataset"]["layers"]["sentiment"] == "awaiting_input"
    # Kunci tidak dikirim sama sekali: UI tidak boleh menemukan angka untuk
    # ditampilkan sebagai hasil ukur.
    for node in payload["graph"]["nodes"]:
        assert "sentiment" not in node


def test_dengan_lapisan_sentimen_simpul_membawa_skor(client_with_sentiment):
    payload = client_with_sentiment.get("/api/bootstrap").json()

    assert payload["dataset"]["layers"]["sentiment"] == "ready"
    nodes = {node["id"]: node for node in payload["graph"]["nodes"]}

    block = nodes["B"]["sentiment"]
    assert block["status"] == "ready"
    assert block["pos"] == 10.0
    assert block["neu"] == 20.0
    assert block["neg"] == 70.0
    # Stance = (pos - neg) / 100, bukan angka yang ditulis tangan.
    assert block["stance"] == -0.6
    assert block["method"] == "inset"
    # Baris sentimen tanpa nilai confidence tetap menghasilkan blok, dengan
    # confidence null — bukan 0 yang terbaca sebagai keyakinan nol.
    assert "sentiment" in nodes["C"]
    assert nodes["C"]["sentiment"]["confidence"] is None


def test_baris_sentimen_bolong_tidak_menjadi_nol():
    """Nilai kosong pada baris sentimen tidak boleh menjadi blok berisi 0.

    Kontrak menandai pos/neu/neg sebagai non-nullable, tetapi artefak bisa
    datang dari pipeline lain. NaN harus berakhir sebagai "tidak ada blok",
    bukan `Pos 0% / Neu 0% / Neg 0%` yang terbaca sebagai terukur netral.
    """
    from types import SimpleNamespace

    from horus_graph.api.serializers import _sentiment_block

    def network_with(score):
        return SimpleNamespace(sentiment=SimpleNamespace(scores={"A": score}))

    complete = {
        "pos": 50.0, "neu": 30.0, "neg": 20.0,
        "method": "inset", "confidence": None,
        "window_start": None, "window_end": None,
    }
    assert _sentiment_block(network_with(complete), "A")["stance"] == 0.3

    for missing in ("pos", "neu", "neg"):
        partial = dict(complete)
        partial[missing] = float("nan")
        assert _sentiment_block(network_with(partial), "A") is None, missing

    # Tanpa baris untuk entitas ini juga tidak ada blok.
    assert _sentiment_block(network_with(complete), "Z") is None


def test_overview_dan_compare(client):
    overview = client.get("/api/graph/overview").json()
    assert overview["total_nodes"] == 4
    assert overview["ego_node"] == "A"

    compare = client.get("/api/graph/compare").json()
    assert compare["available"] is True
    assert compare["baseline_period"] == "e1"
    assert compare["target_period"] == "e2"


def test_dossier_dan_entitas_tidak_dikenal(client):
    dossier = client.get("/api/entities/A")
    assert dossier.status_code == 200
    assert dossier.json()["id"] == "A"

    missing = client.get("/api/entities/tidak-ada")
    assert missing.status_code == 404


def test_rute_dan_kontrafaktual(client):
    route = client.get("/api/analysis/path", params={"origin": "A", "target": "D"}).json()
    assert route["path"] == ["A", "B", "C", "D"]

    removal = client.get("/api/analysis/counterfactual", params={"entity": "B"}).json()
    assert removal["success"] is True
    assert removal["post"]["edges"] < removal["baseline"]["edges"]


def test_peringkat_dan_briefing(client):
    brokers = client.get("/api/analysis/brokers").json()
    assert brokers["ranking"]

    holes = client.get("/api/analysis/holes", params={"mode": "high_autonomy"}).json()
    assert "ranking" in holes

    briefing = client.get("/api/analysis/briefing").json()
    assert briefing["macro"]["nodes"] == 4


def test_bukti_edge_memakai_artikel_yang_benar(client):
    payload = client.get(
        "/api/edges/evidence", params={"source": "A", "target": "B"}
    ).json()

    assert payload["weight"] > 0
    assert payload["evidence"]
    # Panel bukti membaca title dan site; keduanya harus ada di kontrak.
    first = payload["evidence"][0]
    assert first["title"]
    assert first["site"]
    assert first["published_at"]
    assert first["url"].startswith("https://example.test/")
    assert "evidence_snippets" not in payload

    missing = client.get("/api/edges/evidence", params={"source": "A", "target": "D"})
    assert missing.status_code == 404


def test_topik_dan_temporal(client):
    topics = client.get("/api/topics/actor-network").json()
    assert topics["total_topics"] >= 1

    epochs = client.get("/api/temporal").json()["epochs"]
    assert len(epochs) == 3  # e1, e2, all_time


def test_tidak_ada_endpoint_yang_menahan_permintaan(client):
    """
    Analisis berat hanya lewat CLI.

    `/api/enhance` pernah menjalankan null model dan bootstrap di dalam satu GET
    (22 detik pada setelan bawaan, 346 detik pada `resamples=1000`) tanpa satu
    pun pemakai. Batas di bawah longgar; yang dijaga adalah kelasnya: endpoint
    yang menghitung ulang seluruh korpus.
    """
    batas = 1.0
    for path in (
        "/api/health",
        "/api/bootstrap",
        "/api/provenance",
        "/api/temporal",
        "/api/topics/actor-network",
        "/api/analysis/counterfactual?entity=A",
    ):
        mulai = time.perf_counter()
        assert client.get(path).status_code == 200, path
        lama = time.perf_counter() - mulai
        assert lama < batas, f"{path} menahan permintaan {lama:.2f} detik"


def test_tanpa_bundle_mengembalikan_503(tmp_path):
    client = TestClient(create_app(tmp_path / "tidak-ada"))
    response = client.get("/api/bootstrap")

    assert response.status_code == 503
    assert "Bundle" in response.json()["detail"]


def test_bundle_tanpa_ego_tetap_menyajikan_graf(tmp_path, bundle_factory):
    """Dataset tanpa pusat: ego null, graf tetap utuh, tanpa epos."""
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 40) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(40, 80) for e in ("B", "C")]
    bundle = bundle_factory(
        ["A", "B", "C"],
        rows,
        articles=80,
        ego="",
        dates=["2023-06-01"] * 80,
    )
    root = tmp_path / "tanpa-ego"
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
        dataset_id="tanpa-ego",
        date_range=(date(2021, 1, 1), date(2026, 12, 31)),
        generator="tests/noego",
    )

    client = TestClient(create_app(root))
    payload = client.get("/api/bootstrap").json()

    assert payload["presentation"]["ego"] is None
    assert len(payload["graph"]["nodes"]) == 3
    assert payload["epochs"] == []


def test_key_events_memakai_lonjakan_bulanan(client):
    events = client.get("/api/graph/key-events").json()

    assert isinstance(events, list)
    for event in events:
        assert event["date"].endswith("-01")
        assert event["related_actors"] == []
        assert "z =" in event["description"]

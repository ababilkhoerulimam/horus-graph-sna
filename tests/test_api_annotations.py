"""
API anotasi dan laporan.

Dua hal yang dijaga: anotasi menempel pada `snapshot_id` (bukan pada folder
bundle) dan bertahan setelah proses server diganti; laporan yang diunduh
membawa provenance yang sama dengan yang ditampilkan UI.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from horus_graph import annotations as store
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


def _write(root: Path, bundle_factory) -> Path:
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 10) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(10, 20) for e in ("B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(20, 30) for e in ("C", "D")]
    bundle = bundle_factory(["A", "B", "C", "D"], rows, articles=80, ego="A")
    frames = {
        "entities": _pad(bundle.entities, schema.ENTITIES),
        "articles": _pad(bundle.articles, schema.ARTICLES),
        "mentions": _pad(bundle.mentions, schema.MENTIONS),
        "topics": _pad(bundle.topics, schema.TOPICS),
        "article_topics": _pad(bundle.article_topics, schema.ARTICLE_TOPICS),
    }
    write_bundle(
        root,
        frames=frames,
        domain=bundle.domain,
        dataset_id="synthetic",
        date_range=(date(2021, 1, 1), date(2026, 12, 31)),
        generator="tests/api-annotations",
    )
    return root


@pytest.fixture()
def bundle_root(tmp_path, bundle_factory, monkeypatch):
    monkeypatch.setenv(store.DIR_ENV, str(tmp_path / "annotations"))
    return _write(tmp_path / "bundle", bundle_factory)


@pytest.fixture()
def client(bundle_root):
    from horus_graph.api.app import create_app

    return TestClient(create_app(bundle_root))


def test_awalnya_kosong_tanpa_angka(client) -> None:
    payload = client.get("/api/annotations").json()

    assert payload["annotations"] == []
    assert payload["summary"]["total"] == 0
    assert payload["snapshot_id"]


def test_simpan_dan_baca_ulang(client) -> None:
    saved = client.post(
        "/api/annotations",
        json={"target_type": "node", "target_id": "A", "text": "Pusat jaringan"},
    ).json()

    assert saved["status"] == "saved"
    listed = client.get("/api/annotations").json()
    assert [item["text"] for item in listed["annotations"]] == ["Pusat jaringan"]
    assert listed["summary"]["by_target"] == {"node": 1}


def test_simpan_dua_kali_tidak_menggandakan(client) -> None:
    body = {"target_type": "node", "target_id": "A", "text": "sama"}
    client.post("/api/annotations", json=body)
    client.post("/api/annotations", json=body)

    assert len(client.get("/api/annotations").json()["annotations"]) == 1


def test_hapus_menghilangkan_catatan(client) -> None:
    saved = client.post(
        "/api/annotations", json={"target_type": "node", "target_id": "A", "text": "hapus aku"}
    ).json()

    deleted = client.delete(f"/api/annotations/{saved['annotation']['id']}")

    assert deleted.status_code == 200
    assert client.get("/api/annotations").json()["annotations"] == []


def test_hapus_yang_tidak_ada_404(client) -> None:
    assert client.delete("/api/annotations/tidak-ada").status_code == 404


def test_masukan_tidak_sah_ditolak(client) -> None:
    kosong = client.post(
        "/api/annotations", json={"target_type": "node", "target_id": "A", "text": "  "}
    )
    tipe = client.post(
        "/api/annotations", json={"target_type": "berkas", "target_id": "A", "text": "x"}
    )

    assert kosong.status_code == 400
    assert tipe.status_code == 400


def test_anotasi_bertahan_setelah_server_diganti(client, bundle_root) -> None:
    """Proses baru membaca berkas yang sama: catatan bukan state di memori."""
    client.post(
        "/api/annotations", json={"target_type": "graph", "target_id": "", "text": "catatan tetap"}
    )

    from horus_graph.api.app import create_app

    ulang = TestClient(create_app(bundle_root))

    assert [item["text"] for item in ulang.get("/api/annotations").json()["annotations"]] == [
        "catatan tetap"
    ]


def test_menghapus_anotasi_tidak_menyentuh_bundle(client, bundle_root) -> None:
    sebelum = sorted(item.name for item in Path(bundle_root).iterdir())

    saved = client.post(
        "/api/annotations", json={"target_type": "node", "target_id": "A", "text": "x"}
    ).json()
    client.delete(f"/api/annotations/{saved['annotation']['id']}")

    assert sorted(item.name for item in Path(bundle_root).iterdir()) == sebelum


# --- laporan --------------------------------------------------------------


def test_laporan_membawa_snapshot_ambang_dan_batasan(client) -> None:
    response = client.post("/api/report", json={})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    snapshot = client.get("/api/annotations").json()["snapshot_id"]
    assert snapshot in body
    assert "min_support" in body
    assert "Apa yang tidak bisa disimpulkan" in body


def test_laporan_memuat_anotasi_dan_svg(client) -> None:
    client.post(
        "/api/annotations", json={"target_type": "node", "target_id": "B", "text": "catatan laporan"}
    )

    body = client.post(
        "/api/report", json={"svg": '<svg xmlns="http://www.w3.org/2000/svg"><text>ok</text></svg>'}
    ).text

    assert "catatan laporan" in body
    assert "<text>ok</text>" in body


def test_laporan_menyaring_skrip_dari_svg(client) -> None:
    body = client.post(
        "/api/report", json={"svg": '<svg><script>alert(1)</script><text>ok</text></svg>'}
    ).text

    assert "alert(1)" not in body
    assert "<text>ok</text>" in body


def test_laporan_tanpa_svg_tetap_terbaca(client) -> None:
    body = client.post("/api/report", json={}).text

    assert "Kanvas tidak ikut diekspor" in body

def test_tabrakan_id_dijawab_400(client, monkeypatch) -> None:
    monkeypatch.setattr(store, "_identifier", lambda *args: "0123456789ab")
    body = {"target_type": "node", "target_id": "A", "text": "satu"}

    pertama = client.post("/api/annotations", json=body)
    kedua = client.post("/api/annotations", json={**body, "text": "dua"})

    assert pertama.status_code == 200
    assert kedua.status_code == 400
    assert "bertabrakan" in kedua.json()["detail"]

"""
Ekspor GraphML/GEXF/CSV: bentuk berkas, bukan sekadar status 200.

Yang dijaga: jumlah simpul dan sisi sama dengan jaringan, metrik simpul ikut
tertulis, dan angka yang tidak terukur tidak berubah menjadi nol.
"""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from horus_graph.api.app import create_app
from horus_graph.export import formats

GRAPHML_NS = {"g": "http://graphml.graphdrawing.org/xmlns"}
GEXF_NS = {"g": "http://gexf.net/1.2"}


@pytest.fixture()
def client(tmp_path, bundle_factory):
    from tests.test_api import _write_bundle

    root = _write_bundle(tmp_path / "bundle-export", bundle_factory)
    return TestClient(create_app(root))


def test_graphml_memuat_semua_simpul_dan_metrik(client):
    response = client.get("/api/export/graphml")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]

    tree = ET.fromstring(response.text)
    nodes = tree.findall(".//g:node", GRAPHML_NS)
    edges = tree.findall(".//g:edge", GRAPHML_NS)

    bootstrap = client.get("/api/bootstrap").json()
    assert len(nodes) == len(bootstrap["graph"]["nodes"])
    assert len(edges) == len(bootstrap["graph"]["links"])

    kunci = {
        data.get("key")
        for node in nodes
        for data in node.findall("g:data", GRAPHML_NS)
    }
    assert {"label", "degree", "betweenness"} <= kunci


def test_gexf_terbaca_sebagai_gexf(client):
    response = client.get("/api/export/gexf")

    assert response.status_code == 200
    tree = ET.fromstring(response.text)
    assert tree.tag.endswith("gexf")
    assert tree.findall(".//g:node", GEXF_NS)


def test_csv_adalah_daftar_sisi(client):
    response = client.get("/api/export/csv")

    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    bootstrap = client.get("/api/bootstrap").json()

    assert len(rows) == len(bootstrap["graph"]["links"])
    assert set(rows[0]) == {"source", "target", "weight", "npmi", "rescued"}


def test_format_asing_ditolak(client):
    assert client.get("/api/export/xyz").status_code == 404


def test_nilai_tidak_terukur_tidak_menjadi_nol():
    """`NaN`/`None` hilang dari keluaran, bukan ditulis sebagai 0."""
    assert formats._clean(float("nan")) is None
    assert formats._clean(float("inf")) is None
    assert formats._clean(None) is None
    assert formats._clean("") is None
    assert formats._clean(0) == 0
    assert formats._clean(0.0) == 0.0


def test_sel_csv_dikutip_bila_perlu():
    assert formats._csv_cell("Dewa United FC") == "Dewa United FC"
    assert formats._csv_cell("Bali, United") == '"Bali, United"'
    assert formats._csv_cell('Kutip "FC"') == '"Kutip ""FC"""'


def test_ekspor_deterministik(client):
    """Urutan simpul dan sisi tidak bergantung pada urutan dict Python."""
    pertama = client.get("/api/export/graphml").text
    kedua = client.get("/api/export/graphml").text

    assert pertama == kedua

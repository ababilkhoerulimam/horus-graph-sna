"""Ekstraksi metadata tampilan dari visualizer lama (sekali, saat migrasi)."""

from __future__ import annotations

import pytest

from horus_graph.export.legacy_presentation import (
    extract_descriptions,
    extract_milestones,
    split_payload,
)

HTML = """
<html><body><script>
    const TIMELINE_YEARS = [2021, 2022, null];
    const MILESTONES = {
      2021: "2021: Awal",
      2022: "2022: Naik \\"pesat\\"",
      null: "Semua Waktu: Peta Lengkap"
    };
    const ENTITY_DESCRIPTIONS = {
      // komentar diabaikan
      "A": "Aktor utama.",
      "B": "Pendukung, dengan \\"kutip\\" di dalamnya.",
    };
    const LAIN = { "x": "y" };
</script></body></html>
"""


def _index(tmp_path):
    path = tmp_path / "index.html"
    path.write_text(HTML, encoding="utf-8")
    return path


def test_ekstraksi_membaca_kedua_blok(tmp_path):
    index = _index(tmp_path)

    assert extract_descriptions(index) == {
        "A": "Aktor utama.",
        "B": 'Pendukung, dengan "kutip" di dalamnya.',
    }
    assert extract_milestones(index) == {
        "2021": "2021: Awal",
        "2022": '2022: Naik "pesat"',
    }


def test_blok_hilang_ditolak_keras(tmp_path):
    path = tmp_path / "index.html"
    path.write_text("<html></html>", encoding="utf-8")

    with pytest.raises(ValueError, match="ENTITY_DESCRIPTIONS"):
        extract_descriptions(path)


def test_berkas_tidak_ada_ditolak(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_milestones(tmp_path / "tidak-ada.html")


def test_split_payload_memisahkan_deskripsi():
    meta, descriptions = split_payload(
        {
            "title": "Judul",
            "entity_descriptions": {"A": "bio"},
        }
    )

    assert meta.title == "Judul"
    assert descriptions == {"A": "bio"}
    assert "entity_descriptions" not in meta.model_dump()

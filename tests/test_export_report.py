"""
Laporan HTML mandiri.

Yang dijaga: berkas hasilnya bisa diserahkan apa adanya. Karena itu ia harus
memuat `snapshot_id`, ambang, dan seluruh batasan — dan tidak boleh membawa
apa pun yang menjalankan kode saat dibuka, karena SVG datang dari klien.
"""

from __future__ import annotations

from horus_graph.annotations import Annotation
from horus_graph.export.report import render_report, sanitize_svg

PROVENANCE = {
    "software": {"name": "horus-graph", "version": "0.4.1"},
    "contract": {
        "version": "1.2.0",
        "dataset_id": "dewa-united",
        "snapshot_id": "5e0643344153eeb6",
        "snapshot_at": "2026-10-27T00:00:00+00:00",
        "date_range": ["2021-01-01", "2026-12-31"],
        "timezone": "Asia/Jakarta",
    },
    "population": {"articles": 27407, "entities": 77, "mentions": 91234, "dropped_mentions": 3},
    "parameters": {"min_support": 3, "min_npmi": 0.2, "rescued_edges": 8, "seed": 42},
    "metrics": {"nodes": 77, "edges": 475, "density": 0.1623, "modularity": 0.3872},
    "layers": {"sentiment": "awaiting_input"},
    "limitations": [
        "Ko-okurensi mengukur kebersamaan penyebutan, bukan kausalitas.",
        "Ambang support dan NPMI adalah pilihan analis.",
    ],
}


def _annotation(text: str = "Catatan uji") -> Annotation:
    return Annotation(
        id="abc123",
        snapshot_id="5e0643344153eeb6",
        target_type="node",
        target_id="Reva Adi Utama",
        text=text,
        created_at="2026-10-27T10:00:00+00:00",
    )


def test_laporan_memuat_snapshot_dan_ambang() -> None:
    html = render_report(provenance=PROVENANCE)

    assert "5e0643344153eeb6" in html
    assert "min_support" in html and "0.2" in html
    assert "dewa-united" in html


def test_seluruh_limitations_ikut() -> None:
    html = render_report(provenance=PROVENANCE)

    for note in PROVENANCE["limitations"]:
        assert note in html


def test_tanpa_aset_eksternal() -> None:
    html = render_report(provenance=PROVENANCE, svg='<svg xmlns="http://www.w3.org/2000/svg"></svg>')

    assert "<script" not in html.lower()
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in html
    assert "<link" not in html.lower()


def test_anotasi_di_escape() -> None:
    html = render_report(
        provenance=PROVENANCE,
        annotations=[_annotation('<img src=x onerror="alert(1)">')],
    )

    assert "&lt;img" in html
    assert "<img" not in html


def test_svg_dari_klien_disaring() -> None:
    svg = (
        '<svg onload="alert(1)"><script>alert(2)</script>'
        '<a href="javascript:alert(3)"><text>ok</text></a>'
        "<foreignObject></foreignObject></svg>"
    )

    cleaned = sanitize_svg(svg)

    assert "script" not in cleaned.lower()
    assert "onload" not in cleaned.lower()
    assert "javascript:" not in cleaned.lower()
    assert "foreignobject" not in cleaned.lower()
    # Isi gambar yang sah tetap ada.
    assert "<text>ok</text>" in cleaned


def test_svg_kosong_ditulis_sebagai_keterangan() -> None:
    html = render_report(provenance=PROVENANCE, svg=None)

    assert "Kanvas tidak ikut diekspor" in html


def test_tanpa_anotasi_tidak_menulis_nol() -> None:
    html = render_report(provenance=PROVENANCE, annotations=[])

    assert "Belum ada catatan" in html


def test_blok_inferensi_hanya_bila_ada() -> None:
    tanpa = render_report(provenance=PROVENANCE)
    assert "Resolusi uji" not in tanpa

    dengan = render_report(
        provenance={
            **PROVENANCE,
            "inference": {
                "null_model": {
                    "observed": {"modularity": 0.3872},
                    "p_value": {"modularity": None},
                    "z": {"modularity": 27.58},
                    "resamples": 200,
                },
                "p_value_resolution": 0.005,
            },
        }
    )
    assert "Resolusi uji" in dengan
    # Metrik yang tidak teruji ditulis apa adanya, bukan p = 1.
    assert "tidak teruji" in dengan


def test_angka_kunci_menampilkan_nilai_bukan_nama_metode() -> None:
    summary = {
        "nodes": 77,
        "edges": 475,
        "density": 0.1623,
        "communities": {"count": 4, "modularity": 0.3872},
        "transitivity": 0.7352,
        "diameter": 6,
    }

    html = render_report(provenance=PROVENANCE, summary=summary)

    assert "<td>77</td>" in html
    assert "<td>475</td>" in html
    assert "Modularitas (Q)" in html
    # Nama metode punya bagiannya sendiri, tidak bercampur dengan nilai.
    assert "Metode perhitungan" in html


def test_metode_dipisahkan_dari_angka() -> None:
    html = render_report(provenance=PROVENANCE, summary={})

    assert "Metode perhitungan" in html
    assert "Angka kunci" in html
    # Tanpa ringkasan, setiap baris angka kunci ditulis sebagai tanda kosong,
    # bukan 0.
    assert html.count("\u2014") >= 10


def test_nilai_none_ditulis_sebagai_tanda_kosong() -> None:
    html = render_report(
        provenance={**PROVENANCE, "metrics": {"nodes": None, "edges": 475}}
    )

    # Nol tidak pernah menggantikan "tidak ada"; yang muncul tanda kosong.
    assert "\u2014" in html
    assert "<td>0</td>" not in html

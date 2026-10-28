"""
Motif: sensus triad dan rich-club.

Semua angka di sini bisa diperiksa tangan. Sensus triad pada graf tak berarah
hanya punya empat kelas, dan koefisien rich-club mentah adalah
`E_k / C(n_k, 2)` — jumlah sisi di antara simpul berderajat > k dibagi jumlah
pasangan yang mungkin di antara mereka.

Untuk normalisasi, kasus yang paling kuat untuk diuji bukan "rich club ada",
melainkan **"rich club tidak mungkin ada"**: pada graf di mana derajat setiap
simpul memaksa susunan sisinya, setiap graf acak berderajat sama adalah graf
itu sendiri, sehingga rasionya harus tepat 1,0.
"""

from __future__ import annotations

import networkx as nx
import pytest

from horus_graph.core import motifs


def _core_with_leaves(core: int, leaves: int) -> nx.Graph:
    """
    Klien lengkap ditambah daun menggantung.

    Derajatnya memaksa inti tetap lengkap: setiap daun berderajat 1, jadi
    seluruh sisi yang tidak menyentuh daun pasti berada di dalam inti. Karena
    itu tidak ada graf acak lain dengan derajat yang sama.
    """
    graph = nx.complete_graph(core)
    next_id = core
    for node in range(core):
        for _ in range(leaves):
            graph.add_edge(node, next_id)
            next_id += 1
    return graph


# --- sensus triad ----------------------------------------------------------


def test_segitiga_tunggal_tertutup_penuh():
    result = motifs.triad_census(nx.complete_graph(3))

    assert result.status == "ready"
    assert result.counts == {"003": 0, "102": 0, "201": 0, "300": 1}
    assert result.triangles == 1
    assert result.open_wedges == 0
    assert result.closed_share == 1.0


def test_jalur_tiga_simpul_tidak_tertutup():
    result = motifs.triad_census(nx.path_graph(3))

    assert result.counts == {"003": 0, "102": 0, "201": 1, "300": 0}
    assert result.triangles == 0
    assert result.closed_share == 0.0


def test_segitiga_plus_simpul_lepas():
    """Empat simpul → empat triple: satu segitiga dan tiga triple bertepi satu."""
    graph = nx.complete_graph(3)
    graph.add_node("d")

    result = motifs.triad_census(graph)

    assert result.counts == {"003": 0, "102": 3, "201": 0, "300": 1}
    assert result.triples == 4


def test_sensus_triad_butuh_tiga_simpul():
    result = motifs.triad_census(nx.complete_graph(2))

    assert result.status == "awaiting_input"
    assert result.triangles is None
    assert result.reason


def test_sensus_triad_tanpa_sisi_tidak_informatif():
    graph = nx.Graph()
    graph.add_nodes_from("abcd")

    result = motifs.triad_census(graph)

    assert result.status == "awaiting_input"
    assert "tanpa sisi" in (result.reason or "")


# --- rich-club mentah ------------------------------------------------------


def test_rich_club_mentah_bisa_dihitung_tangan():
    """
    Barbell: dua segitiga dihubungkan satu simpul perantara.

    Tujuh simpul, delapan sisi. Untuk k=0 dan k=1, himpunan berderajat > k
    adalah seluruh simpul, jadi rasionya 8/21. Untuk k=2, himpunannya hanya
    dua simpul perantara yang **tidak** bertetangga langsung, jadi 0/1 = 0.
    """
    graph = nx.barbell_graph(3, 1)

    result = motifs.rich_club(graph, normalize=False, min_nodes=2)
    curve = dict(result.coefficients)

    assert result.status == "ready"
    assert curve[0] == 8 / 21
    assert curve[1] == 8 / 21
    assert curve[2] == 0.0


def test_rich_club_mentah_tidak_membawa_rasio():
    result = motifs.rich_club(nx.barbell_graph(3, 1), normalize=False, min_nodes=2)

    assert result.normalized is False
    assert result.ratio == {}
    assert result.peak is None


def test_kurva_dipotong_saat_subgraf_terlalu_kecil():
    graph = nx.barbell_graph(3, 1)

    penuh = motifs.rich_club(graph, normalize=False, min_nodes=2)
    sempit = motifs.rich_club(graph, normalize=False, min_nodes=10)

    assert len(sempit.coefficients) < len(penuh.coefficients)
    assert sempit.truncated == len(penuh.coefficients) - len(sempit.coefficients)


# --- normalisasi -----------------------------------------------------------


def test_derajat_yang_memaksa_memberi_rasio_tepat_satu():
    """
    Kalau derajat sudah menentukan seluruh susunan sisi, tidak ada graf acak
    lain yang bisa dibangun. Rasio setiap ambang harus tepat 1,0 — bukan
    "sekitar 1,0", karena tidak ada yang diacak.
    """
    result = motifs.rich_club(
        _core_with_leaves(6, 3), replicates=3, min_nodes=2, seed=42
    )

    assert result.status == "ready"
    assert result.normalized is True
    assert result.replicates == 3
    for degree, value in result.ratio.items():
        # Pembagian dua angka yang sama bisa menyisakan galat pembulatan.
        assert value == pytest.approx(1.0, abs=1e-9), f"rasio pada derajat {degree} bukan 1,0"


def test_puncak_tidak_memakai_ambang_derajat_nol():
    """
    Rasio pada k=0 selalu 1,0 karena graf acak berderajat sama punya jumlah
    sisi yang sama. Kalau ikut dipertimbangkan, setiap graf tanpa efek
    rich-club akan melaporkan puncak 1,0 pada derajat 0.
    """
    result = motifs.rich_club(
        _core_with_leaves(6, 3), replicates=3, min_nodes=2, seed=42
    )

    assert result.peak is not None
    assert result.peak["degree"] > 0


def test_seed_sama_menghasilkan_rasio_sama():
    graph = nx.gnp_random_graph(30, 0.2, seed=11)

    first = motifs.rich_club(graph, replicates=3, min_nodes=5, seed=5)
    second = motifs.rich_club(graph, replicates=3, min_nodes=5, seed=5)

    assert dict(first.ratio) == dict(second.ratio)


def test_rasio_tidak_pernah_nol_atau_negatif():
    graph = nx.gnp_random_graph(30, 0.15, seed=3)
    result = motifs.rich_club(graph, replicates=4, min_nodes=5, seed=1)

    for value in result.ratio.values():
        if value is not None:
            assert value > 0


def test_graf_klien_penuh_tidak_bisa_dinormalisasi():
    """Graf lengkap tidak punya pertukaran sisi yang sah, jadi tidak ada pembanding."""
    result = motifs.rich_club(nx.complete_graph(5))

    assert result.status == "awaiting_input"
    assert result.reason


def test_graf_tanpa_sisi_menunggu_masukan():
    result = motifs.rich_club(nx.Graph())

    assert result.status == "awaiting_input"
    assert result.coefficients == {}


# --- blok gabungan ---------------------------------------------------------


def test_blok_tanpa_rich_club_menyebut_alasannya():
    block = motifs.motif_block(motifs.triad_census(nx.complete_graph(3)))

    assert block["triads"]["status"] == "ready"
    assert block["rich_club"]["status"] == "awaiting_input"
    assert "motifs" in block["rich_club"]["reason"]


def test_blok_dengan_rich_club_memakai_hasil_yang_dihitung():
    club = motifs.rich_club(nx.barbell_graph(3, 1), normalize=False, min_nodes=2)

    block = motifs.motif_block(motifs.triad_census(nx.complete_graph(3)), club)

    assert block["rich_club"]["status"] == "ready"
    assert block["rich_club"]["normalized"] is False


def test_koefisien_mentah_tidak_dikirim_tanpa_pembanding():
    """Tanpa null model, kurva mentah naik secara konstruksi — bukan bukti."""
    import networkx as nx

    result = motifs.rich_club(nx.barbell_graph(4, 1), normalize=False, min_nodes=2)

    payload = result.as_dict()
    assert payload["normalized"] is False
    assert "coefficients" not in payload

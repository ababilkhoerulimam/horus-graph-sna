"""
Lapisan opsional dua arah: tanpa data semua `None`, dengan data semua terisi.

Setiap test di sini punya pasangan shell: satu memastikan engine tidak
mengarang angka saat lapisan kosong, satu lagi memastikan angka benar-benar
dipakai saat lapisan tersedia.
"""

from __future__ import annotations

import pandas as pd
import pytest

from horus_graph.analysis import entity_dossier, sentiment_ranking, simulate_removal, trace_path
from horus_graph.api.serializers import _sentiment_block
from horus_graph.core import build_network


def _transmission(rows) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "src",
            "dst",
            "alpha",
            "alpha_ci_low",
            "alpha_ci_high",
            "lead_time_min",
            "method",
            "n_events",
            "window_start",
            "window_end",
        ],
    )


def _sentiment(rows) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "entity_id",
            "pos",
            "neu",
            "neg",
            "method",
            "confidence",
            "window_start",
            "window_end",
        ],
    )


def _corpus(bundle_factory, **kwargs):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 14) for e in ("B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(14, 20) for e in ("A", "M2")]
    return bundle_factory(["A", "B", "C", "M1", "M2", "M3"], rows, articles=100, ego="A", **kwargs)


def test_tanpa_lapisan_semua_none(bundle_factory):
    network = build_network(_corpus(bundle_factory))
    assert network.transmission is None
    assert network.sentiment is None
    assert network.layers == {"transmission": "awaiting_input", "sentiment": "awaiting_input"}
    assert network.provenance()["layers"]["transmission"]["edges"] == 0


def test_transmisi_terbaca_menjadi_graf_terarah(bundle_factory):
    frame = _transmission(
        [
            ("M1", "M2", 0.5, 0.4, 0.6, 30.0, "hawkes_exp", 12, None, None),
            ("M2", "M3", 0.4, 0.3, 0.5, 60.0, "hawkes_exp", 8, None, None),
        ]
    )
    network = build_network(_corpus(bundle_factory, transmission=frame))

    assert network.layers["transmission"] == "ready"
    wire = network.transmission.graph
    assert wire.number_of_edges() == 2
    assert wire["M1"]["M2"]["alpha"] == 0.5
    assert wire["M1"]["M2"]["lead_time_min"] == 30.0
    assert network.transmission.severed_routes("M2") == 2


def test_transmisi_dengan_n_events_kosong_tidak_crash(bundle_factory):
    frame = _transmission(
        [("M1", "M2", 0.5, 0.4, 0.6, 30.0, "hawkes_exp", None, None, None)]
    )
    network = build_network(_corpus(bundle_factory, transmission=frame))
    assert network.transmission.graph["M1"]["M2"]["n_events"] is None


def test_sentimen_terbaca_menjadi_skor(bundle_factory):
    frame = _sentiment(
        [
            ("A", 60.0, 20.0, 20.0, "lexicon", 0.9, None, None),
            ("B", 30.0, 30.0, 40.0, "lexicon", 0.8, None, None),
        ]
    )
    network = build_network(_corpus(bundle_factory, sentiment=frame))

    assert network.layers["sentiment"] == "ready"
    assert network.sentiment.n_entities == 2
    assert network.sentiment.method == "lexicon"
    assert network.sentiment.scores["A"]["neg"] == 20.0


def test_rute_media_memakai_graf_kawat(bundle_factory):
    frame = _transmission(
        [
            ("M1", "M2", 0.5, 0.4, 0.6, 30.0, "hawkes_exp", 12, None, None),
            ("M2", "M3", 0.4, 0.3, 0.5, 60.0, "hawkes_exp", 8, None, None),
        ]
    )
    network = build_network(_corpus(bundle_factory, transmission=frame))
    result = trace_path(network, "M1", "M3")

    assert result["success"] is True
    assert result["route"] == "wire"
    assert result["path"] == ["M1", "M2", "M3"]
    assert result["has_hawkes"] is True
    assert result["product_alpha"] == pytest.approx(0.2)
    assert result["total_lead_time_min"] == pytest.approx(90.0)
    assert all(hop["is_hawkes"] for hop in result["hops"])


def test_rute_kawat_ke_entitas_memakai_satu_hop_kawat(bundle_factory):
    frame = _transmission(
        [("M1", "M2", 0.5, 0.4, 0.6, 30.0, "hawkes_exp", 12, None, None)]
    )
    network = build_network(_corpus(bundle_factory, transmission=frame))
    # M1 tidak menyebut siapa pun di korpus, jadi satu-satunya jalan adalah kawat.
    result = trace_path(network, "M1", "A")

    assert result["success"] is True
    assert result["route"] == "wire_bridge"
    assert result["path"][0] == "M1"
    assert result["path"][1] == "M2"
    assert result["hops"][0]["is_hawkes"] is True
    assert result["hops"][-1]["is_hawkes"] is False
    assert result["product_alpha"] == pytest.approx(0.5)


def test_tanpa_transmisi_rute_media_tetap_ko_okurensi(bundle_factory):
    network = build_network(_corpus(bundle_factory))
    result = trace_path(network, "A", "C")
    assert result["route"] == "cooccurrence"
    assert result["has_hawkes"] is False


def test_penghapusan_menghitung_rute_terputus(bundle_factory):
    frame = _transmission(
        [
            ("M1", "M2", 0.5, 0.4, 0.6, 30.0, "hawkes_exp", 12, None, None),
            ("M2", "M3", 0.4, 0.3, 0.5, 60.0, "hawkes_exp", 8, None, None),
        ]
    )
    network = build_network(_corpus(bundle_factory, transmission=frame))
    result = simulate_removal(network, "M2")
    assert result["severed_causal_routes"] == 2


def test_tanpa_transmisi_rute_terputus_nol(bundle_factory):
    network = build_network(_corpus(bundle_factory))
    assert simulate_removal(network, "B")["severed_causal_routes"] == 0


def test_dossier_sentimen_siap_dihitung(bundle_factory):
    frame = _sentiment([("A", 60.0, 20.0, 20.0, "lexicon", 0.9, None, None)])
    network = build_network(_corpus(bundle_factory, sentiment=frame))

    dossier = entity_dossier(network, "A")
    assert dossier["sentiment"]["status"] == "ready"
    assert dossier["sentiment"]["stance"] == pytest.approx(0.4)
    assert dossier["sentiment"]["method"] == "lexicon"

    missing = entity_dossier(network, "B")["sentiment"]
    assert missing["status"] == "missing"
    assert missing["stance"] is None


def test_penghapusan_membawa_stance_simpul_yang_hilang(bundle_factory):
    frame = _sentiment([("B", 20.0, 30.0, 50.0, "lexicon", 0.9, None, None)])
    network = build_network(_corpus(bundle_factory, sentiment=frame))
    assert simulate_removal(network, "B")["lost_sentiment_impact"] == pytest.approx(-0.3)


def test_peringkat_sentimen_shell(bundle_factory):
    network = build_network(_corpus(bundle_factory))
    result = sentiment_ranking(network)
    assert result["status"] == "awaiting_input"
    assert result["ranking"] == []


def test_peringkat_sentimen_siap(bundle_factory):
    frame = _sentiment(
        [
            ("A", 60.0, 20.0, 20.0, "lexicon", 0.9, None, None),
            ("B", 30.0, 30.0, 40.0, "lexicon", 0.8, None, None),
        ]
    )
    network = build_network(_corpus(bundle_factory, sentiment=frame))
    result = sentiment_ranking(network, kind="negative", limit=2)

    assert result["status"] == "ready"
    assert result["evaluated"] == 2
    assert [item["id"] for item in result["ranking"]] == ["B", "A"]
    assert result["ranking"][0]["neg"] == 40.0
    assert result["ranking"][0]["stance"] == pytest.approx(-0.1)


def test_peringkat_sentimen_menolak_jenis_lain(bundle_factory):
    network = build_network(_corpus(bundle_factory))
    with pytest.raises(ValueError):
        sentiment_ranking(network, kind="netral")


def test_stance_empat_panel_memakai_rumus_yang_sama(bundle_factory):
    """
    Dossier, peringkat, kontrafaktual, dan blok API harus memberi angka identik.

    Baris di bawah sengaja berjumlah 99.7, bukan 100: dengan penyebut hardcoded
    100.0, tiga panel melaporkan 0.097 sementara peringkat melaporkan 0.0973.
    Simpulnya B, bukan A, karena ego tidak boleh dihapus di simulasi.
    """
    frame = _sentiment([("B", 39.7, 30.0, 30.0, "lexicon", 0.9, None, None)])
    network = build_network(_corpus(bundle_factory, sentiment=frame))

    dossier = entity_dossier(network, "B")["sentiment"]["stance"]
    ranking = sentiment_ranking(network, kind="negative", limit=1)["ranking"][0]["stance"]
    removed = simulate_removal(network, "B")["lost_sentiment_impact"]
    block = _sentiment_block(network, "B")["stance"]

    assert dossier == ranking == removed == block
    assert dossier == pytest.approx(9.7 / 99.7, abs=1e-4)

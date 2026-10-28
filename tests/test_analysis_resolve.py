"""Resolusi nama entitas: urutan pencarian harus deterministik."""

from __future__ import annotations

from horus_graph.analysis import resolve_candidates, resolve_entity, unresolved_share
from horus_graph.core import build_network


def _network(bundle_factory):
    bundle = bundle_factory(
        ["Egy Maulana Vikri", "Liga 1", "Persib Bandung"],
        [
            ("art000", "Egy Maulana Vikri", 1),
            ("art000", "Liga 1", 1),
            ("art001", "Persib Bandung", 1),
        ],
        articles=3,
    )
    return build_network(bundle)


def test_id_persis_menang(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "Liga 1") == "Liga 1"


def test_case_insensitive(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "liga 1") == "Liga 1"
    assert resolve_entity(network, "EGY MAULANA VIKRI") == "Egy Maulana Vikri"


def test_substring_mencocokkan_id(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "egy") == "Egy Maulana Vikri"
    assert resolve_entity(network, "persib") == "Persib Bandung"


def test_query_kosong_dan_tidak_dikenal_mengembalikan_none(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "") is None
    assert resolve_entity(network, "   ") is None
    assert resolve_entity(network, "entitas-yang-tidak-ada") is None


def test_spasi_di_tepi_diabaikan(bundle_factory):
    network = _network(bundle_factory)
    assert resolve_entity(network, "  Liga 1  ") == "Liga 1"


# --- normalisasi, alias, dan ambiguitas ------------------------------------


def _labelled(bundle_factory, ids, labels, aliases=None, rows=None):
    from dataclasses import replace

    bundle = bundle_factory(
        ids,
        rows or [("art000", ids[0], 1)],
        articles=3,
    )
    entities = bundle.entities.assign(label=list(labels))
    if aliases is not None:
        entities = entities.assign(aliases=aliases)
    return build_network(replace(bundle, entities=entities))


def test_alias_menyelesaikan_kueri(bundle_factory):
    network = _labelled(
        bundle_factory,
        ["E1", "E2"],
        ["Egy Maulana Vikri", "Persib Bandung"],
        aliases=[["EMV", "Egy M"], None],
    )

    assert resolve_entity(network, "EMV") == "E1"
    assert resolve_entity(network, "egy m") == "E1"


def test_alias_kalah_dari_label_persis(bundle_factory):
    """Alias adalah lapis keempat; label persis tetap menang."""
    network = _labelled(
        bundle_factory,
        ["E1", "E2"],
        ["Persib", "Persib Bandung"],
        aliases=[[], ["Persib"]],
    )

    assert resolve_entity(network, "Persib") == "E1"


def test_aksen_dan_tanda_baca_dinormalkan(bundle_factory):
    network = _labelled(bundle_factory, ["E1"], ["Égy Maulana-Vikri"])

    assert resolve_entity(network, "egy maulana vikri") == "E1"
    assert resolve_entity(network, "EGY  MAULANA--VIKRI") == "E1"


def test_dua_kandidat_pada_lapis_yang_sama_dianggap_ambigu(bundle_factory):
    network = _labelled(bundle_factory, ["E1", "E2"], ["Andi Pratama", "Andi Wijaya"])

    assert resolve_entity(network, "andi") is None
    assert resolve_candidates(network, "andi") == ["E1", "E2"]


def test_kandidat_kosong_saat_jawabannya_tunggal(bundle_factory):
    network = _labelled(bundle_factory, ["E1", "E2"], ["Andi Pratama", "Budi"])

    assert resolve_candidates(network, "andi") == []
    assert resolve_candidates(network, "tidak-ada") == []


def test_unresolved_share_sesuai_hitungan_manual(bundle_factory):
    # "Andi" adalah label E1 sekaligus substring label E2 dan E3: kueri "Andi"
    # mengembalikan E1 (label persis), jadi ketiganya tetap bisa dicari.
    # E4 dan E5 berlabel sama, sehingga label itu ambigu untuk keduanya.
    network = _labelled(
        bundle_factory,
        ["E1", "E2", "E3", "E4", "E5"],
        ["Andi", "Andi Pratama", "Andi Wijaya", "Kembar", "Kembar"],
    )

    report = unresolved_share(network)

    assert report["entities"] == 5
    assert report["unresolved"] == 2
    assert report["unresolved_share"] == 0.4
    assert report["unresolved_ids"] == ["E4", "E5"]


def test_unresolved_share_katalog_kosong(bundle_factory):
    network = _labelled(bundle_factory, ["E1"], ["Satu"])

    report = unresolved_share(network)

    assert report["unresolved_share"] == 0.0
    assert report["unresolved_ids"] == []

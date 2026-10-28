"""Kontrak bundle: satu fixture sah, lalu satu mutasi per kode temuan."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from horus_graph.contract import Domain, Epoch, schema, validate_bundle
from horus_graph.io import BundleInvalid, load_bundle, write_bundle

DATE_RANGE = (date(2021, 1, 1), date(2026, 12, 31))


def _frames() -> dict[str, pd.DataFrame]:
    return {
        "entities": pd.DataFrame(
            {
                "entity_id": ["Ego FC", "Person A", "Media X"],
                "entity_type": ["Organization", "Person", "Source"],
                "label": ["Ego FC", "Person A", "Media X"],
                "aliases": [["ego"], [], ["mediax"]],
                "first_seen": ["2021-01-01", None, "2021-06-01"],
            }
        ),
        "articles": pd.DataFrame(
            {
                "article_id": ["a1", "a2", "a3"],
                "source_id": ["Media X", "Media X", "Media X"],
                "published_at": [
                    "2021-03-01T10:00:00Z",
                    "2023-07-15T08:30:00Z",
                    "2026-01-02T00:00:00Z",
                ],
                "url_hash": ["u1", "u2", "u3"],
                "title": ["t1", "t2", "t3"],
                "lang": ["id", "id", "id"],
                "dedupe_group": [None, "g1", "g1"],
                "word_count": [300, 250, 400],
            }
        ),
        "mentions": pd.DataFrame(
            {
                "article_id": ["a1", "a1", "a2", "a3"],
                "entity_id": ["Ego FC", "Person A", "Ego FC", "Ego FC"],
                "count": [2, 1, 3, 1],
                "confidence": [0.9, 0.7, 0.95, 0.8],
                "matcher_version": ["v1", "v1", "v1", "v1"],
            }
        ),
        "topics": pd.DataFrame(
            {
                "topic_id": ["transfer", "taktik"],
                "label": ["Transfer", "Taktik"],
                "keywords": [["transfer"], ["taktik"]],
            }
        ),
        "article_topics": pd.DataFrame(
            {
                "article_id": ["a1", "a2", "a3"],
                "topic_id": ["transfer", "taktik", "taktik"],
                "score": [0.8, 0.6, 0.9],
            }
        ),
    }


def _domain() -> Domain:
    return Domain(
        domain_id="test-league",
        ego_id="Ego FC",
        label="Ego FC",
        league="Liga Uji",
        entity_types=["Organization", "Person", "Source"],
        epochs=[
            Epoch(id="epoch_1", label="Awal", start_year=2021, end_year=2022),
            Epoch(id="epoch_2", label="Akhir", start_year=2023, end_year=2026),
        ],
    )


def _write(root: Path, frames: dict[str, pd.DataFrame] | None = None) -> Path:
    write_bundle(
        root,
        frames=frames or _frames(),
        domain=_domain(),
        dataset_id="test",
        date_range=DATE_RANGE,
        generator="pytest",
        generator_version="0",
    )
    return root


def _codes(findings) -> set[str]:
    return {f.code for f in findings if f.level == "error"}


def test_bundle_sah_lolos_tanpa_temuan(tmp_path):
    root = _write(tmp_path / "bundle")
    assert validate_bundle(root) == []


def test_loader_mengembalikan_counts_dan_status_layer(tmp_path):
    bundle = load_bundle(_write(tmp_path / "bundle"))
    assert bundle.counts()["entities"] == 3
    assert bundle.counts()["mentions"] == 4
    assert bundle.layer_status("transmission") == "awaiting_input"
    assert bundle.layer_status("sentiment") == "awaiting_input"
    assert bundle.domain.ego_id == "Ego FC"


def test_loader_tidak_membaca_parquet_dua_kali(tmp_path, monkeypatch):
    root = _write(tmp_path / "bundle")
    dibaca: list[str] = []
    asli = pq.read_table

    def hitung(path, *args, **kwargs):
        dibaca.append(Path(path).name)
        return asli(path, *args, **kwargs)

    monkeypatch.setattr(pq, "read_table", hitung)
    load_bundle(root)

    assert dibaca, "loader tidak membaca parquet sama sekali"
    assert len(dibaca) == len(set(dibaca)), f"parquet dibaca ulang: {dibaca}"


def test_loader_tanpa_validasi_membaca_data_yang_sama(tmp_path):
    root = _write(tmp_path / "bundle")
    ketat = load_bundle(root)
    longgar = load_bundle(root, strict=False)

    assert longgar.counts() == ketat.counts()
    assert list(longgar.articles.columns) == list(ketat.articles.columns)
    assert longgar.layer_status("sentiment") == "awaiting_input"


def test_loader_menolak_bundle_rusak(tmp_path):
    frames = _frames()
    frames["entities"] = pd.concat([frames["entities"], frames["entities"].iloc[[0]]])
    root = _write(tmp_path / "bundle", frames)
    with pytest.raises(BundleInvalid):
        load_bundle(root)


def test_primary_key_duplikat(tmp_path):
    frames = _frames()
    frames["entities"] = pd.concat([frames["entities"], frames["entities"].iloc[[0]]])
    codes = _codes(validate_bundle(_write(tmp_path / "bundle", frames)))
    assert "primary_key_duplicate" in codes


def test_penerbit_di_luar_entities_hanya_peringatan(tmp_path):
    """source_id adalah penerbit, bukan aktor; tidak harus ada di entities."""
    frames = _frames()
    frames["articles"].loc[0, "source_id"] = "Media Hantu"
    findings = validate_bundle(_write(tmp_path / "bundle", frames))
    assert "source_not_in_entities" in {f.code for f in findings if f.level == "warn"}
    assert not [f for f in findings if f.level == "error"]


def test_mention_menunjuk_entitas_asing(tmp_path):
    frames = _frames()
    frames["mentions"].loc[0, "entity_id"] = "Entitas Hantu"
    codes = _codes(validate_bundle(_write(tmp_path / "bundle", frames)))
    assert "foreign_key_violation" in codes


def test_tanggal_di_luar_rentang(tmp_path):
    frames = _frames()
    frames["articles"].loc[0, "published_at"] = "2019-05-01T00:00:00Z"
    codes = _codes(validate_bundle(_write(tmp_path / "bundle", frames)))
    assert "published_at_out_of_range" in codes


def test_tanggal_tidak_bisa_diparse(tmp_path):
    frames = _frames()
    frames["articles"].loc[0, "published_at"] = "kemarin sore"
    codes = _codes(validate_bundle(_write(tmp_path / "bundle", frames)))
    assert "published_at_invalid" in codes


def test_url_hash_duplikat(tmp_path):
    frames = _frames()
    frames["articles"].loc[1, "url_hash"] = frames["articles"].loc[0, "url_hash"]
    codes = _codes(validate_bundle(_write(tmp_path / "bundle", frames)))
    assert "url_hash_duplicate" in codes


def test_sentimen_tidak_berjumlah_100(tmp_path):
    frames = _frames()
    frames["sentiment"] = pd.DataFrame(
        {
            "entity_id": ["Ego FC"],
            "pos": [10.0],
            "neu": [10.0],
            "neg": [10.0],
            "method": ["indobert"],
            "confidence": [0.9],
            "window_start": [None],
            "window_end": [None],
        }
    )
    codes = _codes(validate_bundle(_write(tmp_path / "bundle", frames)))
    assert "sentiment_sum_invalid" in codes


def test_alpha_ci_tidak_mengapit(tmp_path):
    frames = _frames()
    frames["transmission"] = pd.DataFrame(
        {
            "src": ["Media X"],
            "dst": ["Ego FC"],
            "alpha": [0.4],
            "alpha_ci_low": [0.5],
            "alpha_ci_high": [0.9],
            "lead_time_min": [120.0],
            "method": ["mle"],
            "n_events": [10],
            "window_start": [None],
            "window_end": [None],
        }
    )
    codes = _codes(validate_bundle(_write(tmp_path / "bundle", frames)))
    assert "alpha_ci_invalid" in codes


def test_manifest_mengklaim_ready_tanpa_isi(tmp_path):
    root = _write(tmp_path / "bundle")
    manifest_path = root / schema.MANIFEST
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["layers"] = {"transmission": "ready"}
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    codes = _codes(validate_bundle(root))
    assert "layer_status_mismatch" in codes


def test_versi_kontrak_mayor_berbeda(tmp_path):
    root = _write(tmp_path / "bundle")
    manifest_path = root / schema.MANIFEST
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["contract_version"] = "2.0.0"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    codes = _codes(validate_bundle(root))
    assert "contract_version_mismatch" in codes


def test_kolom_wajib_hilang(tmp_path):
    root = _write(tmp_path / "bundle")
    frames = _frames()["entities"].drop(columns=["label"])
    table = pa.Table.from_pandas(frames, preserve_index=False)
    pq.write_table(table, root / "entities.parquet")

    codes = _codes(validate_bundle(root))
    assert "schema_missing_columns" in codes


def test_counts_tidak_cocok(tmp_path):
    root = _write(tmp_path / "bundle")
    manifest_path = root / schema.MANIFEST
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["counts"]["entities"] = 99
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    codes = _codes(validate_bundle(root))
    assert "count_mismatch" in codes


def test_ego_tidak_ada_di_entitas(tmp_path):
    frames = _frames()
    frames["entities"].loc[0, "entity_id"] = "Bukan Ego"
    frames["mentions"].loc[frames["mentions"]["entity_id"] == "Ego FC", "entity_id"] = "Bukan Ego"
    frames["articles"]["source_id"] = "Media X"
    codes = _codes(validate_bundle(_write(tmp_path / "bundle", frames)))
    assert "ego_not_in_entities" in codes


def test_ego_kosong_diterima_sebagai_tanpa_pusat(tmp_path):
    """`ego_id` kosong = dataset tanpa simpul pusat, bukan pelanggaran."""
    frames = _frames()
    frames["entities"].loc[0, "entity_id"] = "Bukan Ego"
    frames["mentions"].loc[frames["mentions"]["entity_id"] == "Ego FC", "entity_id"] = "Bukan Ego"
    frames["articles"]["source_id"] = "Media X"

    root = tmp_path / "bundle"
    write_bundle(
        root,
        frames=frames,
        domain=_domain().model_copy(update={"ego_id": ""}),
        dataset_id="test",
        date_range=DATE_RANGE,
        generator="pytest",
        generator_version="0",
    )
    assert "ego_not_in_entities" not in _codes(validate_bundle(root))


def _syndication_frame(titles, sources, groups):
    import pandas as pd

    return pd.DataFrame(
        {
            "title": titles,
            "published_at": ["2024-01-01T00:00:00Z"] * len(titles),
            "source_id": sources,
            "dedupe_group": groups,
        }
    )


def test_sindikasi_tanpa_dedupe_group_dilaporkan():
    from horus_graph.contract.validate import _check_syndication

    findings = []
    _check_syndication(
        _syndication_frame(
            ["Klasemen Liga", "klasemen liga", "Klasemen  Liga", "Lain"],
            ["a", "b", "c", "d"],
            [None, None, None, None],
        ),
        findings,
    )

    assert [item.code for item in findings] == ["syndication_suspected"]
    assert findings[0].level == "warn"


def test_sindikasi_terlabel_tidak_dilaporkan():
    from horus_graph.contract.validate import _check_syndication

    findings = []
    _check_syndication(
        _syndication_frame(
            ["Klasemen Liga"] * 3,
            ["a", "b", "c"],
            ["g1", "g1", "g1"],
        ),
        findings,
    )

    assert findings == []


def test_sindikasi_dua_artikel_tidak_dilaporkan():
    from horus_graph.contract.validate import _check_syndication

    findings = []
    _check_syndication(
        _syndication_frame(["Klasemen Liga"] * 2, ["a", "b"], [None, None]),
        findings,
    )

    assert findings == []



# --- sentimen tingkat artikel (kontrak 1.3) --------------------------------


def _article_sentiment(article_ids=("a1", "a2", "a3")) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "article_id": list(article_ids),
            "pos": [70.0, 20.0, 50.0],
            "neu": [20.0, 30.0, 30.0],
            "neg": [10.0, 50.0, 20.0],
            "method": ["lexicon"] * len(article_ids),
            "confidence": [0.8, 0.6, None],
        }
    )


def test_tanpa_sentimen_artikel_bundle_tetap_sah(tmp_path):
    bundle = load_bundle(_write(tmp_path / "bundle"))

    assert bundle.layer_status("article_sentiment") == "awaiting_input"
    assert bundle.has_article_sentiment is False
    assert bundle.counts()["article_sentiment"] == 0


def test_sentimen_artikel_dibaca_sebagai_lapisan_tersendiri(tmp_path):
    frames = _frames()
    frames["article_sentiment"] = _article_sentiment()
    bundle = load_bundle(_write(tmp_path / "bundle", frames))

    assert bundle.layer_status("article_sentiment") == "ready"
    assert bundle.has_article_sentiment is True
    assert bundle.counts()["article_sentiment"] == 3
    # Lapisan entitas tidak ikut berubah karena tabel artikel ada.
    assert bundle.layer_status("sentiment") == "awaiting_input"


def test_sentimen_artikel_dengan_id_asing_ditolak(tmp_path):
    frames = _frames()
    frames["article_sentiment"] = _article_sentiment(("a1", "a2", "a99"))

    assert "foreign_key_violation" in _codes(validate_bundle(_write(tmp_path / "b", frames)))


def test_sentimen_artikel_negatif_ditolak(tmp_path):
    frames = _frames()
    frame = _article_sentiment()
    frame.loc[0, "neg"] = -5.0
    frames["article_sentiment"] = frame

    assert "sentiment_negative_value" in _codes(validate_bundle(_write(tmp_path / "b", frames)))

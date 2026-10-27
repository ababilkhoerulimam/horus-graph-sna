"""
Anotasi per snapshot.

Yang dijaga: catatan menempel pada isi bundle (bukan foldernya), tidak pernah
menyentuh berkas bundle, dan menekan simpan dua kali tidak menghasilkan dua
catatan.
"""

from __future__ import annotations

import json

import pytest

from horus_graph import annotations as store


@pytest.fixture(autouse=True)
def _isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DIR_ENV, str(tmp_path / "annotations"))


def test_tulis_baca_hapus() -> None:
    record = store.add("abc123", "node", "Reva Adi Utama", "Bek kiri, pindah dari Madura")

    assert store.load("abc123") == [record]
    assert store.remove("abc123", record.id) is True
    assert store.load("abc123") == []


def test_idempoten_pada_isi_yang_sama() -> None:
    first = store.add("abc123", "node", "A", "catatan")
    second = store.add("abc123", "node", "A", "catatan")

    assert first.id == second.id
    assert len(store.load("abc123")) == 1


def test_teks_berbeda_menghasilkan_catatan_berbeda() -> None:
    store.add("abc123", "node", "A", "catatan satu")
    store.add("abc123", "node", "A", "catatan dua")

    assert len(store.load("abc123")) == 2


def test_snapshot_berbeda_tidak_bercampur() -> None:
    store.add("aaa", "node", "A", "milik a")
    store.add("bbb", "node", "A", "milik b")

    assert [item.text for item in store.load("aaa")] == ["milik a"]
    assert [item.text for item in store.load("bbb")] == ["milik b"]


def test_hapus_yang_tidak_ada_mengembalikan_false() -> None:
    assert store.remove("abc123", "tidak-ada") is False


def test_catatan_kosong_ditolak() -> None:
    with pytest.raises(store.AnnotationError):
        store.add("abc123", "node", "A", "   ")


def test_target_type_di_luar_daftar_ditolak() -> None:
    with pytest.raises(store.AnnotationError):
        store.add("abc123", "berkas", "A", "catatan")


def test_simpul_tanpa_id_ditolak() -> None:
    with pytest.raises(store.AnnotationError):
        store.add("abc123", "node", "", "catatan")


def test_catatan_graf_tidak_butuh_target() -> None:
    record = store.add("abc123", "graph", "", "ambang dinaikkan ke 5")

    assert record.target_type == "graph"


def test_teks_kepanjangan_ditolak() -> None:
    with pytest.raises(store.AnnotationError):
        store.add("abc123", "node", "A", "x" * (store.TEXT_MAX_CHARS + 1))


def test_snapshot_id_tidak_bisa_keluar_folder(tmp_path) -> None:
    with pytest.raises(store.AnnotationError):
        store.path_for("../../etc/passwd")


def test_berkas_rusak_dibaca_sebagai_kosong(tmp_path) -> None:
    path = store.path_for("abc123")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{rusak", encoding="utf-8")

    assert store.load("abc123") == []


def test_berkas_ditulis_atomik_tanpa_sisa_tmp() -> None:
    store.add("abc123", "node", "A", "catatan")

    files = sorted(item.name for item in store.path_for("abc123").parent.iterdir())

    assert files == ["abc123.json"]


def test_berkas_memuat_snapshot_id() -> None:
    store.add("abc123", "node", "A", "catatan")

    payload = json.loads(store.path_for("abc123").read_text(encoding="utf-8"))

    assert payload["snapshot_id"] == "abc123"
    assert payload["annotations"][0]["target_id"] == "A"


def test_ringkasan_menghitung_per_target() -> None:
    store.add("abc123", "node", "A", "satu")
    store.add("abc123", "node", "B", "dua")
    store.add("abc123", "graph", "", "tiga")

    summary = store.summarise(store.load("abc123"))

    assert summary == {"total": 3, "by_target": {"node": 2, "graph": 1}}

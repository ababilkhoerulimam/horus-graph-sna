"""
Sesi copilot: di memori atau di SQLite, dengan perilaku yang sama.

Yang dijaga: restart tidak menghilangkan riwayat, isi pesan utuh termasuk
perintah kanvas, dan penghapusan benar-benar menghapus — bukan hanya
menyembunyikan dari daftar sementara barisnya tetap ada di berkas.
"""

from __future__ import annotations

import pytest

from horus_graph.copilot.sessions import SessionStore


@pytest.fixture()
def store(tmp_path):
    return SessionStore(str(tmp_path / "sessions.db"))


def test_sesi_bertahan_setelah_store_baru(tmp_path) -> None:
    path = str(tmp_path / "sessions.db")
    pertama = SessionStore(path)
    sesi = pertama.create_session("Uji persistensi")
    pertama.append_message(sesi["id"], "user", "Siapa broker utama?")
    pertama.append_message(sesi["id"], "assistant", "Budi.", agent_name="copilot")

    kedua = SessionStore(path)
    daftar = kedua.list_sessions()

    assert [item["id"] for item in daftar] == [sesi["id"]]
    assert daftar[0]["message_count"] == 2
    pesan = kedua.get_session_messages(sesi["id"])
    assert [item["role"] for item in pesan] == ["user", "assistant"]
    assert pesan[1]["agent_name"] == "copilot"


def test_judul_diambil_dari_pesan_pertama_dan_ikut_tersimpan(tmp_path) -> None:
    path = str(tmp_path / "sessions.db")
    pertama = SessionStore(path)
    sesi = pertama.create_session()
    pertama.append_message(sesi["id"], "user", "Siapa jembatan antara dua gugus?")

    kedua = SessionStore(path)

    assert kedua.list_sessions()[0]["title"].startswith("Siapa jembatan")


def test_perintah_kanvas_utuh_setelah_dimuat_ulang(tmp_path) -> None:
    path = str(tmp_path / "sessions.db")
    pertama = SessionStore(path)
    sesi = pertama.create_session()
    perintah = {"action": "focus", "node": "A"}
    pertama.append_message(sesi["id"], "assistant", "Fokus ke A.", canvas_command=perintah)

    kedua = SessionStore(path)
    pesan = kedua.get_session_messages(sesi["id"])

    assert pesan[0]["canvas_command"] == perintah


def test_hapus_sesi_menghapus_barisnya(tmp_path) -> None:
    path = str(tmp_path / "sessions.db")
    pertama = SessionStore(path)
    sesi = pertama.create_session()
    pertama.append_message(sesi["id"], "user", "Halo")

    assert pertama.delete_session(sesi["id"]) is True
    kedua = SessionStore(path)

    assert kedua.list_sessions() == []
    assert kedua.get_session_messages(sesi["id"]) == []


def test_tanpa_path_tetap_di_memori(tmp_path) -> None:
    """Perilaku lama tidak berubah: tanpa berkas, sesi hidup selama proses."""
    store = SessionStore()
    sesi = store.create_session("Sementara")

    assert [item["id"] for item in store.list_sessions()] == [sesi["id"]]
    assert SessionStore().list_sessions() == []


def test_penulisan_berulang_tidak_menggandakan_sesi(tmp_path) -> None:
    path = str(tmp_path / "sessions.db")
    store = SessionStore(path)
    sesi = store.create_session("Satu")
    store.append_message(sesi["id"], "user", "Halo")
    store.append_message(sesi["id"], "user", "Lagi")

    kedua = SessionStore(path)

    assert len(kedua.list_sessions()) == 1
    assert kedua.list_sessions()[0]["message_count"] == 2

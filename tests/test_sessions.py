"""
Sesi copilot: di memori atau di SQLite, dengan perilaku yang sama.

Yang dijaga: restart tidak menghilangkan riwayat, isi pesan utuh termasuk
perintah kanvas, dan penghapusan benar-benar menghapus — bukan hanya
menyembunyikan dari daftar sementara barisnya tetap ada di berkas.
"""

from __future__ import annotations

import pytest

from horus_graph.copilot import sessions
from horus_graph.copilot.sessions import MAX_SESSIONS, SessionStore


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

def test_muat_hanya_sesi_terbaru(tmp_path) -> None:
    """
    Batas 50 adalah batas memori, bukan batas penyimpanan: 60 sesi di DB
    harus menghasilkan 50 di memori dan 60 baris yang tetap utuh.
    """
    path = str(tmp_path / "sessions.db")
    pertama = SessionStore(path)
    # Pesan ditulis sebelum sesi ini tergusur dari memori proses pertama.
    ids = [pertama.create_session("Sesi 0")["id"]]
    pertama.append_message(ids[0], "user", "Pesan lama")
    ids += [pertama.create_session(f"Sesi {index}")["id"] for index in range(1, 60)]

    kedua = SessionStore(path)

    assert len(kedua.list_sessions()) == MAX_SESSIONS
    assert kedua._db is not None
    assert kedua._db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 60
    # Sesi yang tergusur dari memori belum dimuat...
    assert kedua.get_session_messages(ids[0]) == []
    # ...tetapi id yang dipegang drawer mengembalikan riwayatnya, bukan sesi kosong.
    assert kedua.ensure_session(ids[0])["message_count"] == 1
    assert [item["content"] for item in kedua.get_session_messages(ids[0])] == ["Pesan lama"]


def test_eviksi_tidak_menghapus_baris(tmp_path) -> None:
    path = str(tmp_path / "sessions.db")
    store = SessionStore(path)
    ids = [store.create_session(f"Sesi {index}")["id"] for index in range(MAX_SESSIONS + 1)]

    assert ids[0] not in {item["id"] for item in store.list_sessions()}
    assert store._db is not None
    assert store._db.execute(
        "SELECT COUNT(*) FROM sessions WHERE id = ?", (ids[0],)
    ).fetchone()[0] == 1


def test_create_app_selalu_memasang_store(tmp_path) -> None:
    """Tanpa ini, aplikasi kedua dalam satu proses memakai store aplikasi pertama."""
    from horus_graph.api.app import create_app

    sessions.configure_store(str(tmp_path / "lain.db"))
    sessions.get_session_store().create_session("Milik aplikasi lama")

    try:
        create_app(session_db=None)
        assert sessions.get_session_store().list_sessions() == []
    finally:
        sessions.configure_store(None)

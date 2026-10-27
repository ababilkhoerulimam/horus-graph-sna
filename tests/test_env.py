"""Pemuatan `.env` lokal: shell menang, berkas hanya menambal yang kosong."""

from __future__ import annotations

import os
from pathlib import Path

from horus_graph.env import load_env_file


def test_berkas_tidak_ada_bukan_error(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "tidak-ada.env") == 0


def test_komentar_dan_baris_kosong_dilewati(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HORUS_UJI_A", raising=False)
    berkas = tmp_path / ".env.local"
    berkas.write_text("# komentar\n\nHORUS_UJI_A=nilai\nbukan-pasangan\n", encoding="utf-8")

    assert load_env_file(berkas) == 1
    assert os.environ["HORUS_UJI_A"] == "nilai"


def test_variabel_yang_sudah_ada_tidak_ditimpa(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HORUS_UJI_B", "dari-shell")
    berkas = tmp_path / ".env.local"
    berkas.write_text("HORUS_UJI_B=dari-berkas\n", encoding="utf-8")

    assert load_env_file(berkas) == 0
    assert os.environ["HORUS_UJI_B"] == "dari-shell"


def test_tanda_kutip_di_ujung_dibuang(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HORUS_UJI_C", raising=False)
    berkas = tmp_path / ".env.local"
    berkas.write_text('HORUS_UJI_C="bernilai spasi"\n', encoding="utf-8")

    load_env_file(berkas)

    assert os.environ["HORUS_UJI_C"] == "bernilai spasi"

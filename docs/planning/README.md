# Planning horus-graph

Folder ini adalah satu-satunya tempat status pekerjaan dicatat. Kode, tes, dan
commit tetap jadi kebenaran akhir; dokumen di sini menjelaskan **mengapa** dan
**seberapa jauh** sesuatu sudah jalan.

## Isi

| Berkas | Isi |
| --- | --- |
| [`AUDIT.md`](AUDIT.md) | Temuan audit 2026-10-27: bukti, angka terukur, dan alasan tiap keputusan |
| [`ROADMAP.md`](ROADMAP.md) | Fase 0–3 dengan kotak centang (selesai) |
| [`IMPROVEMENTS.md`](IMPROVEMENTS.md) | Fase V: visualisasi & SNA sampai kelas enterprise — diagnosis, keputusan arsitektur, 12 butir |

## Konvensi

- `- [ ]` belum dikerjakan, `- [x]` selesai. Coret saat selesai, jangan hapus.
- Setiap butir punya **kriteria terima** yang bisa diperiksa tanpa membaca kode.
- Bila sebuah butir dibatalkan, tulis ~~coret~~ + satu baris alasan. Jangan
  dibuang, supaya keputusan lama tidak diulang.
- Angka acuan (77 simpul / 475 sisi / 0,1623) dipakai untuk membandingkan
  sebelum-sesudah. Kalau bundle golden berubah, perbarui di satu tempat:
  `tests/conftest.py`.

## Aturan main

1. **Integritas sebelum fitur.** Selama masih ada angka yang tampil tanpa
   status `ready`, tidak ada pekerjaan lain yang boleh mendahuluinya.
2. **Satu fase, satu commit range.** Jangan mencampur perbaikan integritas
   dengan refactor UX.
3. **Tes dulu untuk setiap bug.** Butir yang lahir dari bug wajib punya tes
   yang gagal sebelum diperbaiki.
4. **Jangan menambah permukaan baru** (endpoint, modul, opsi CLI) tanpa
   menghapus satu yang setara. Repo ini sudah 9.179 baris Python + 8.544 baris
   frontend untuk satu pengguna.

## Status ringkas

| Fase | Isi | Butir | Selesai |
| --- | --- | --- | --- |
| 0 | Integritas data di UI | 5 | 5 |
| 1 | Performa & startup | 8 | 7 + 1 batal |
| 2 | UX + aksesibilitas | 10 | 10 |
| 3 | Lapisan enterprise | 8 | 8 |
| — | Pemangkasan (cut list) | 7 | 7 |
| V | Visualisasi & SNA kelas enterprise | 12 | 8 |

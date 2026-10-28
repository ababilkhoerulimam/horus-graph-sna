# Rencana — mutu analisis jaringan menuju 10/10

Dokumen kerja, bukan dokumen arsitektur. Isinya urutan perbaikan supaya mutu
**analisis jaringan** naik dari 7,5 ke 10, bukan keamanan atau operasional —
keduanya sudah diputuskan tidak dikejar untuk demo ini.

Aturan repo tetap: satu fase satu rentang commit, tanpa dependensi baru,
`ruff` dan `mypy` bersih, dokumen dan pesan commit berbahasa Indonesia, dan
setiap butir ditutup hanya bila kriteria terimanya bisa diperiksa mesin.

Snapshot saat dokumen ditulis (HEAD `b58f27f`): **633 lulus / 23 skip**,
`mypy` bersih atas 77 berkas, `data/bundles/` kosong sehingga seluruh tes baru
memakai fixture `bundle_factory`, bukan bundle emas.

Legenda: `[ ]` belum · `[~]` dikerjakan · `[x]` selesai.
Effort: **XS** < 30 menit · **S** 1–2 jam · **M** ±setengah hari · **L** > 1 hari.

---

## 0. Lima fakta yang mengubah rencana

Dibaca dari kode, bukan dari dokumen lama. Tiga di antaranya membuat butir
termahal menjadi jauh lebih murah.

| # | Temuan | Bukti | Akibat |
| --- | --- | --- | --- |
| T1 | Uji hipergeometrik dan BH-FDR **sudah ada**, nol pemanggil | `core/association.py:77`, `:100` | Signifikansi tepi = menyambungkan + tes paritas, bukan menulis statistik baru |
| T2 | Kolom `dedupe_group` ada di kontrak, tidak pernah dibaca engine | `contract/schema.py:58`; satu-satunya pemakaian `tests/test_contract.py:43` | Dedup sindikasi tidak butuh perubahan kontrak |
| T3 | Kolom `aliases` ada di kontrak, dibuang saat build | `contract/schema.py:22` vs `core/build.py:202` (hanya tiga kolom) | Resolusi alias = 1 baris di build + logika pencarian |
| T4 | Sentimen hanya per entitas, tidak per artikel | `contract/schema.py:104-115`, `core/layers.py:38` | Analisis bertanda belum bisa dipertanggungjawabkan (lihat D6) |
| T5 | Pembentukan pasangan dari insidensi diduplikasi | `core/cooccurrence.py:81-92` vs `enhance/bootstrap.py:126-153` | Wajib disatukan **sebelum** `Cooccurrence` ditambah field |

---

## 1. Keputusan desain

Delapan titik yang tidak bisa diputuskan sambil menulis kode. Yang dipilih
ditebalkan.

| # | Keputusan | Dipilih | Ditolak | `contract_version` |
| --- | --- | --- | --- | --- |
| D1 | Null asosiasi | **curveball pada matriks insidensi, kedua margin tetap** | konfigurasi bipartit; swap pada proyeksi | tetap 1.2.0 |
| D2 | Signifikansi tepi | **hipergeometrik satu sisi + BH-FDR atas seluruh pasangan teramati** | permutasi per tepi; z-score tanpa koreksi | tetap 1.2.0 |
| D3 | Resolusi entitas | **alias diputuskan ingest, pencarian di analysis; ambigu → `None` + kandidat** | fuzzy di analysis; merge di engine | 1.3.0 (manifest opsional) |
| D4 | Dedup sindikasi | **`dedupe_group` = hash (judul ternormalisasi, tanggal UTC), diisi ingest** | URL kanonik; hash isi | 1.3.0 (flag manifest) |
| D5 | Kesepakatan peringkat | **Kendall tau-b + Jaccard top-10** | Spearman; rata-rata \|Δrank\| | tetap 1.2.0 |
| D6 | Jaringan bertanda | **tidak diterbitkan** sampai ada polaritas per artikel | tanda = sign(stance_u × stance_v); varians stance per komunitas | 1.3.0 (tabel opsional) |
| D7 | CI pergeseran peringkat | **bootstrap artikel berpasangan, unit = artikel/grup** | bootstrap simpul; CI analitik | tetap 1.2.0 |
| D8 | Validasi eksternal | **label JSONL di luar bundle, precision@k + recall@k** | label di dalam bundle; AUC global | tetap 1.2.0 |

**D1 — kenapa bukan proyeksi.** NPMI didefinisikan pada margin insidensi
(`support/total` versus `node_articles/total`). Hanya null yang menjaga derajat
artikel **dan** entitas yang membuat sebaran NPMI sebanding dengan nilai
teramati. `degree_preserving_null` (`enhance/nullmodel.py:79`) menjawab
pertanyaan lain — "apakah susunan tepi wajar" — dan tetap dipakai untuk
modularitas/transitivitas dengan nama `topology_null`; yang baru bernama
`association_null`. Dua pertanyaan, dua null, dua nama.

**D2 — keluarga uji.** BH dijalankan atas **semua pasangan dengan support ≥ 1**.
Menjalankannya hanya atas pasangan yang sudah lolos `min_support`/`min_npmi`
membuat q tidak sah: sebagian uji disembunyikan sebelum koreksi.
`min_npmi` turun pangkat menjadi lantai efek yang dilaporkan, bukan gerbang.

**D3 — perilaku yang sengaja berubah.** Pencarian yang menemukan lebih dari
satu kandidat mengembalikan `None` beserta daftar kandidat, bukan kandidat
pertama. "Pertama menang" membuat jawaban bergantung urutan baris parquet —
bug yang tidak terlihat sampai bundle ditulis ulang.

**D4 — jebakan normalisasi judul.** Yang dibuang: sufiks sumber (" - Portal X"),
tanda baca, emoji, diakritik, spasi ganda, kapitalisasi. Yang **tidak** boleh
dibuang: angka (skor "2-1", tahun, nomor pekan). Kunci wajib menyertakan
tanggal UTC karena judul generik ("Klasemen") bertabrakan antar berita; grup
dibatasi ≤ 8 artikel dan yang lebih besar dilaporkan sebagai
`oversized_groups`, bukan digabung diam-diam.

**D6 — kenapa tidak.** Tanda tepi hanya bisa diturunkan dari dua atribut
simpul, jadi indeks keseimbangan mengukur aritmetika atribut, bukan valensi
relasional; pada komunitas homogen hasilnya selalu "seimbang" dan pembaca akan
membacanya sebagai temuan tentang hubungan antar aktor. Pintu masuknya
disiapkan (tabel `article_sentiment`), rumusnya ditetapkan sekarang supaya
tidak ada dua definisi nanti, tetapi tidak ada angka yang diterbitkan.

---

## 2. Urutan fase

```
F1 masukan ──► F2 seleksi tepi ──► F3 nama & peringkat ──► F4 kalibrasi
```

Empat ketergantungan keras, bukan selera:

1. **Dedup (F1) sebelum FDR dan null (F2).** Ia mengubah `support` dan `total`,
   yaitu masukan bagi NPMI, backbone, null, dan FDR. Mengerjakannya belakangan
   berarti menghitung ulang dua butir.
2. **FDR sebelum null.** Null harus menjalankan pipeline seleksi yang sama
   dengan graf teramati, termasuk gerbang `min_q`.
3. **Satu konstruktor insidensi sebelum field baru.** Tanpa itu, penambahan
   `p_value`/`q_value` menyentuh tiga berkas sekaligus.
4. **Null sebelum validasi eksternal.** precision@k di atas ambang heuristik
   hanya mengukur heuristiknya.

| Fase | Isi | Butir | Risiko | Status |
| --- | --- | --- | --- | --- |
| F1 | Masukan yang jujur: satu jalur insidensi, dedup, alias dibawa | F1.1–F1.4 | sedang (denominator berubah) | `[x]` `bd425e4..187c1ff` |
| F2 | Seleksi tepi yang bisa dipertanggungjawabkan | F2.1–F2.5 | tinggi (angka bergeser, artefak lama) | `[x]` `544de1b..5de2710` |
| F3 | Nama dan peringkat | F3.1–F3.3 | sedang (perilaku resolve berubah) | `[x]` `d75ba9c..a6d67ac` |
| F4 | Kalibrasi eksternal dan ketidakpastian | F4.1–F4.4 | rendah | `[x]` `9c33234..8a6bc76` |

Gerbang tiap fase: `make check` (ruff + mypy + pytest) hijau.

---


## 3. Butir per fase

### F1 — masukan yang jujur

| Butir | Perubahan | Kriteria terima | Effort |
| --- | --- | --- | --- |
| F1.1 | Satu konstruktor `from_incidence` + `graph_from_cooccurrence` di `core/cooccurrence.py`; `enhance/bootstrap.py` dan `core/build.py` memakainya | `cooccurrence(bundle)` identik field demi field dengan `from_incidence(cooc.incidence, ...)`; 633 tes lama lulus tanpa diubah | S |
| F1.2 | Dedup: `support` per grup, `total` = grup + singleton, `articles_raw`, flag `manifest.dedup`, blok `population` melaporkan keduanya | 3 artikel satu grup menyebut A+B → `support(A,B) == 1` dan `total` turun 3; tanpa kolom terisi angka identik dengan sebelumnya | S |
| F1.3 | Sindikasi tak terlabel dilaporkan: ≥ 3 artikel judul sama + tanggal sama + sumber beda + `dedupe_group` null → satu temuan `warn` | tepat 1 temuan pada kasus itu; 0 temuan bila `dedupe_group` terisi; 0 temuan untuk 2 artikel | S |
| F1.4 | `aliases` ikut dibawa `core/build.py:202` ke `NetworkBundle` (belum dipakai pencarian) | `network.aliases[entity_id]` memuat alias dari bundle; bundle tanpa alias → daftar kosong, bukan `None` | XS |

Catatan F1.2: default aktif tetapi **no-op bila kolom kosong**, dan
`--no-dedup` di CLI tersedia untuk membandingkan. Artefak lama tetap terbaca
karena bentuk `Cooccurrence` tidak berubah.

### F2 — seleksi tepi yang bisa dipertanggungjawabkan

| Butir | Perubahan | Kriteria terima | Effort |
| --- | --- | --- | --- |
| F2.1 | `hypergeometric_p_array` (vektor) + `q_value` di `from_incidence`; BH atas seluruh pasangan support ≥ 1 | vektor ≡ skalar (`approx 1e-12`); BH known-answer `[0.01,0.02,0.03,0.5]` → `[0.04,0.04,0.04,0.5]`; q ≥ p dan monoton | M |
| F2.2 | `BackboneConfig.min_q` (default `None`), atribut tepi `q`, `BackboneReport` melaporkan `tested_pairs`/`significant_pairs`/`min_q` | `min_q=None` mereproduksi seleksi lama (`array_equal`); pasangan yang lolos support + NPMI tetapi q > ambang gugur, dan penyelamatan tidak menghidupkannya lagi | S |
| F2.3 | Kurva sensitivitas ketiga `by_q` | `passed` tidak berkurang saat `min_q` naik (arah q terbalik dari ambang lain); ambang aktif selalu ada di grid | S |
| F2.4 | `association_null` (curveball) + `topology_null` (nama baru untuk yang lama) | tiap draw: margin baris **dan** kolom identik dengan aslinya; seed sama → identik; graf dua klik: modularitas teramati > null | L |
| F2.5 | Artefak inferensi v2 + blok `edge_significance` ringkas (indeks integer, bukan string) | `method_version` 1 → basi; panjang `u`/`v`/q = jumlah tepi backbone; artefak 475 tepi < 20 KB | S |


Tiga kriteria di tabel ini dikoreksi saat implementasi; semuanya salah asumsi,
bukan salah hitung:

1. **BH.** Contoh `[0.01,0.04,0.03,0.5]` menghasilkan `[0.04, 0.0533, 0.0533, 0.5]`
   — 0,04 ada di peringkat 3, jadi 0,04 × 4/3. Jawaban `[0.04,0.04,0.04,0.5]`
   benar untuk `[0.01,0.02,0.03,0.5]`, dan itulah yang diuji.
2. **`min_q` tidak bisa diuji dengan p = 0,3.** p sebesar itu berarti pasangan
   tidak berasosiasi, dan NPMI-nya ikut mendekati 0 sehingga sudah gugur di
   `min_npmi` sebelum gerbang q sempat bekerja. Yang diuji: pasangan yang lolos
   support + NPMI tetapi q-nya di atas ambang.
3. **Arah q terbalik.** `q <= 0,05` adalah 5% FDR: ambang lebih besar berarti
   lebih longgar. Kurva `by_q` karena itu tidak menurun, dan UI harus memberi
   label sendiri alih-alih menumpang sumbu `min_support`.
4. **Null insidensi membuat proyeksi lebih padat, bukan lebih jarang.** Pada dua
   klik terpisah, pengacakan menyebar entitas antarartikel sehingga pasangan
   lintas klik ikut lolos ambang (36,8 vs 20 sisi). Statistik pembedanya
   modularitas (0,50 vs 0,09), dan itulah yang diuji.
Catatan F2.4: biaya turun, bukan naik — satu sweep curveball ≈ 5 ms pada
nnz ≈ 5 ribu, 200 draw × 5 sweep ≈ 5 detik, menggantikan ≈ 50 detik
`double_edge_swap`. Pada 10.000 simpul, `resamples` dipotong ke 100 dan
`sweeps` ke 3, dan kedua angka itu ditulis ke artefak.

### F3 — nama dan peringkat

| Butir | Perubahan | Kriteria terima | Effort |
| --- | --- | --- | --- |
| F3.1 | `resolve_entity`: normalisasi (NFKD, casefold, tanda baca), urutan id → label → alias → substring, ambigu → `None` + `resolve_candidates`; `unresolved_share` diukur pada label katalog | alias "EMV" menyelesaikan kueri; "andi" pada label "Andi Pratama"/"Andi Wijaya" → `None` + 2 kandidat; `unresolved_share` = hitungan manual | M |
| F3.2 | `rank_agreement`: tau-b (seri dikoreksi), Jaccard top-10, `betweenness_weighted` (jarak `1/support`, bukan `support`); enam varian | identik 1,0; terbalik −1,0; known-answer 0,6; `None` dibuang berpasangan; `coverage < 0,5` → status `insufficient` | M |
| F3.3 | Endpoint `/api/analysis/agreement` (6 varian + `prominence` di lapisan API) | matriks simetris, diagonal 1,0; `prominence` ada di daftar varian | S |

Dua kriteria F3 dikoreksi saat implementasi:

1. **"Andi" tidak ambigu bila ada entitas berlabel "Andi".** Label persis
   adalah lapis kedua, jadi ia menang atas "Andi Pratama" di lapis substring.
   Yang benar-benar ambigu: dua label yang sama-sama hanya *mengandung* kueri.
2. **`unresolved_share` tidak bisa diukur dari kueri pengguna**, karena tidak
   ada batch kueri di sistem. Ukurannya diambil dari katalog: entitas yang
   labelnya tidak mengembalikan dirinya sendiri (label ganda, atau label yang
   menunjuk entitas lain) — cacat data, bukan salah ketik.

Catatan F3.2: `prominence` sengaja tidak masuk `metric_agreement` — ia bobot
tampilan (0,45/0,35/0,20), bukan metrik analisis; memasukkannya membuat
kesepakatan bergantung pada pilihan UI.

### F4 — kalibrasi eksternal dan ketidakpastian

| Butir | Perubahan | Kriteria terima | Effort |
| --- | --- | --- | --- |
| F4.1 | Tabel opsional `article_sentiment` (1.3.0), lapisan `awaiting_input` bila tidak ada | bundle tanpa tabel tetap sah; `layer_status == "awaiting_input"`; FK dan nilai negatif ditolak | M |
| F4.2 | Tegakkan D6: keluaran bertanda = status + alasan, tanpa kunci numerik | tidak ada satu pun kunci angka pada keluaran itu | XS |
| F4.3 | CI pergeseran peringkat antar-epos (bootstrap berpasangan, unit artikel/grup) | CI stabil pada seed sama; epos < 2 artikel → `None` + alasan; `betweenness_approx` ditandai bila dipakai | L |
| F4.4 | Evaluator label JSONL: precision@k, recall@k, `coverage`; `HORUS_LABELS` opsional | precision@2 = 1,0 eksak pada label tertanam; tanpa env → tes `skip`, bukan gagal | M |

---


## 4. Rencana commit

| Rentang | Commit |
| --- | --- |
| F1 | `refactor(cooccurrence): satu jalur pembentukan pasangan` · `feat(core): dedup sindikasi lewat dedupe_group` · `feat(contract): sindikasi tak terlabel dilaporkan` · `refactor(build): aliases dibawa ke NetworkBundle` |
| F2 | `feat(core): nilai-p hipergeometrik dan BH-FDR pada seleksi tepi` · `feat(core): null model pada matriks insidensi` · `feat(api): artefak inferensi versi 2` |
| F3 | `feat(analysis): resolusi entitas sadar alias dan ambiguitas` · `feat(analysis): kesepakatan peringkat antar-varian metrik` |
| F4 | `feat(contract): tabel opsional sentimen per artikel` · `feat(analysis): selang kepercayaan pergeseran peringkat epos` · `feat(analysis): evaluasi presisi@k terhadap label eksternal` |

---

Catatan F4: implementasi menyimpang dari tabel di dua tempat, dan keduanya
disengaja.

1. **`article_sentiment` tidak dipakai untuk analisis bertanda.** Tabel itu
   per artikel, sedangkan tanda tepi butuh polaritas per (artikel, entitas).
   Ia tetap berguna (agregasi, bukti), tetapi D6 tidak berubah karenanya.
2. **Batas betweenness aproksimasi 500 simpul, bukan 2.000.** 200 draw ×
   betweenness eksak pada 2.000 simpul sudah menit-menitan; ambang 500
   menjaga fungsi ini tetap bisa dipanggil tanpa menjadi artefak terjadwal.

## 5. Sengaja tidak dikerjakan

- **ERGM / model generatif** — butuh dependensi baru dan puluhan parameter untuk
  graf 77 simpul; null curveball menjawab pertanyaan yang sama dengan biaya jauh
  lebih kecil.
- **Hypergraph / motif orde tinggi** — data tidak memberi keanggotaan ganda yang
  bisa dipertanggungjawabkan per artikel.
- **Uji power-law** — pada n = 77, uji itu tidak punya daya; angka p akan
  mengesankan tanpa arti.
- **Leiden penuh** — konsensus Louvain multi-seed sudah memberi stabilitas yang
  dilaporkan lewat ARI.
- **Keseimbangan triad / polarisasi** — D6: tidak ada polaritas relasional.
- **Fuzzy matching tanpa review** — ambang kemiripan mengubah graf secara senyap.
- **Dependensi baru** (python-igraph, statsmodels, rapidfuzz) — aturan repo.

---

## 6. Batasan yang tetap terbuka setelah F4

| Batasan | Sebab | Penutup yang disarankan |
| --- | --- | --- |
| Tidak ada analisis bertanda | Polaritas hanya per entitas dan per artikel; tidak ada polaritas per (artikel, entitas) | Butuh ekstraksi aspek di pipeline; tanda tepi tetap tidak diterbitkan (D6) |
| precision@k bergantung label pakar | Tidak ada ground truth publik untuk korpus ini | Mulai dari 20–30 label per kasus; laporkan `coverage` selalu |
| Curveball mahal pada graf sangat padat | Satu sweep = O(nnz); 10.000 × 200.000 butuh ratusan detik | Turunkan `resamples`, atau pindahkan ke artefak terjadwal |
| Betweenness aproksimasi pada n > 500 | O(n·m) per draw | Ditandai `betweenness_approx: true`; jangan sembunyikan |

---

## 7. Peta skor

| Setelah | Skor | Alasan |
| --- | --- | --- |
| Sekarang | 7,5 | Metrik dan ketidakpastian ada; seleksi tepi masih heuristik, nama belum terselesaikan |
| F1 | 8,0 | Denominator jujur, sindikasi tidak lagi menggandakan dukungan |
| F2 | 9,0 | Tepi punya dasar uji; null menjawab pertanyaan yang benar |
| F3 | 9,5 | Nama dan peringkat tidak lagi bergantung keberuntungan urutan baris |
| F4 | 10 | Ada kalibrasi eksternal dan ketidakpastian temporal; klaim yang tidak bisa dipertanggungjawabkan sengaja tidak dibuat |


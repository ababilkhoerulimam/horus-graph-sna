# Rencana perbaikan — 19 temuan audit Fase V

Dokumen kerja, bukan dokumen arsitektur. Isinya daftar cacat yang sudah
diverifikasi beserta urutan perbaikannya, supaya pengerjaan bisa dilacak butir
per butir. Aturan repo tetap berlaku: satu fase satu rentang commit, tanpa
dependensi baru, `ruff` dan `mypy` bersih, dan setiap butir ditutup hanya bila
kriteria terimanya lulus mesin.

Legenda status: `[ ]` belum · `[~]` sedang dikerjakan · `[x]` selesai ·
`[!]` dibatalkan (sebutkan alasannya di baris itu).

Legenda effort: **XS** < 30 menit · **S** 1–2 jam · **M** ±setengah hari ·
**L** > 1 hari.

---

## Ringkasan audit

Audit dijalankan empat reviewer paralel (plugin ECC) ditambah probe langsung
terhadap kode, bukan terhadap dokumen. Hasil mekanis pada saat audit:
**542 tes lulus, 23 skip** (penyebabnya `data/bundles/` tidak ada), `ruff`
bersih, `mypy` bersih atas 76 berkas.

| Tingkat | Jumlah | Inti |
| --- | --- | --- |
| CRITICAL | 1 | Sanitasi SVG laporan bisa dilewati; laporan yang dibagikan mengeksekusi JS |
| HIGH | 4 | Audit menggagalkan permintaan; identitas lolos jadi admin; `is_anchor` masih gerbang label; filter kanvas no-op senyap |
| MEDIUM | 8 | Rate limit/audit tidak merata, koefisien rich-club mentah, nilai mentah di sequence, artefak inferensi tanpa snapshot, `NODE_COLUMNS`, kartu topik-aktor, `size_rank` mati, V2.2 belum di-commit |
| LOW | 6 | `null` jadi 0, id anotasi 12 hex, batas sesi, token di query, angka dokumen usang |

Daftar lengkap per butir ada di [Lampiran A](#lampiran-a--19-temuan-terverifikasi).

---

## Ringkasan fase

| Fase | Isi | Butir | Risiko | Status |
| --- | --- | --- | --- | --- |
| A | Ruang kerja bersih (commit V2.2 yang menggantung) | 19 | rendah | `[x]` |
| B | Tutup kebocoran: sanitasi, audit, identitas, token | 1, 2, 3, 17 | sedang | `[x]` |
| C | Kontrak & semantik API | 7, 10, 8, 9, 11, 14 | sedang–tinggi | `[x]` |
| D | Frontend setara: gerbang visual, label, kanvas, ukuran | 6, 4, 5, 13, 12 | tinggi (kanvas) | `[x]` |
| E | Operasional & dokumen | 16, 15, 18 | rendah | `[x]` |

Ketergantungan: `A → B → C → D → E`. B2 dan B3 menjadi prasyarat C1; B3 menjadi
prasyarat C4; D1 → D3 → D4; E3 terakhir.

---

## Fase A — ruang kerja bersih

**Selesai 2026-10-28.** Tiga commit, pohon bersih sesudahnya, gerbang hijau
(542 lulus / 23 skip, `ruff` dan `mypy` bersih).

| Butir | Perubahan | Kriteria terima | Effort | Status |
| --- | --- | --- | --- | --- |
| 19 | Tiga commit terpisah: alat + tesnya; `Makefile`; dua dokumen | `git status --porcelain` kosong; pytest tetap 542/23 | S | `[x]` |

Dua koreksi ikut masuk karena reviewer menolak menandai V2.2 selesai dengan
angka yang salah: tes visual **30 kasus** (bukan 17), dan anggaran piksel
**120 px absolut** (bukan porsi 0,1%, yang 12× lebih longgar di lebar 1600).
Selisih-diri jadi **6,7 kali** di bawah anggaran, bukan 66. `visual` juga
didaftarkan di `.PHONY`.

---

## Fase B — tutup kebocoran

| Butir | Perubahan | Kriteria terima | Effort | Status |
| --- | --- | --- | --- | --- |
| **1** CRITICAL | Ganti denylist regex dengan **allowlist + rebuild pohon memakai `html.parser`** (`convert_charrefs=True`), serialisasi ulang dari nol, root `<svg xmlns>` ditulis sendiri. Tanpa `href`/`xlink:href`/`src`/`style`/`image`/`use`/`foreignObject`. Batas 2 MB, 20.000 elemen, depth 32. Gagal → placeholder. Tambah `<meta CSP default-src 'none'>` sebagai lapis kedua | 28 kasus adversarial lulus; setiap keluaran lolos regex `(?i)<\s*script\|\son[a-z]+\s*=\|javascript:\|https?://\|@import\|<image\|<foreignobject` = None; SVG sah mempertahankan jumlah `<circle>` | M | `[x]` |
| **2** HIGH | Audit per kelas operasi: **egress** → 200 + `X-Audit-Status: failed`; **mutasi idempoten** → 200 + header; **mutasi tak-idempoten** → audit **sebelum** tulis, gagal → 503 tanpa perubahan. Baris gagal ditulis `logger.error` utuh + counter `/metrics` + `threading.Lock` pada append | Status 200/503 tepat; tidak ada baris audit hilang tanpa jejak; DELETE gagal membuat catatan tetap ada | S | `[x]` |
| **3** HIGH | Invarian: `Identity('local','admin')` **hanya** bila `TRUSTED=0` dan `TOKEN` kosong. `TRUSTED=1` tanpa header → **401**. Satu resolver dipakai HTTP **dan** WS; WS gagal → `close(1008)` sebelum `accept()`. Sanitasi `actor` (tolak karakter kontrol, >128 karakter) | Matriks 14 kombinasi env × header × token lulus; tidak ada `source=="local"` saat gerbang menyala | S | `[x]` |
| **17** LOW | HTTP: `request_token()` hanya header, halaman pertama pindah ke `#token=` lalu `replaceState`. WS: **tidak ditambal**, dicatat sebagai batasan + `Referrer-Policy: no-referrer`. Tiket sekali-pakai menjadi syarat bila server keluar dari loopback | `GET /api/bootstrap?token=…` → 401; batasan tercatat | S | `[x]` |

> **Kenapa `html.parser`, bukan `xml.etree`.** Laporan dibuka browser sebagai
> HTML, jadi tokenizer HTML adalah parser acuan. `ElementTree` memberi pohon
> gratis tetapi memakai model namespace XML yang tidak sama dengan yang
> diterapkan browser pada HTML.

---

## Fase C — kontrak & semantik API

| Butir | Perubahan | Kontrak | Kriteria terima | Effort | Status |
| --- | --- | --- | --- | --- | --- |
| 7 | `DELETE /api/annotations` masuk bucket `annotations` **yang sama** dengan POST (kalau beda bucket, penyerang mendapat 30+30). `POST /api/annotations`, `/api/report`, `/api/export` dapat `require_role("analyst")`. WS: bucket `chat`, `delete_session` butuh analyst, audit `chat.session.create/delete` dan `chat.query` tanpa isi pesan. Urutan tetap: identitas → 403 → 429 → mutasi → audit | perilaku | 429 pada permintaan ke-31; viewer 403; tiga aksi baru muncul di JSONL | M | `[x]` |
| 10 | Artefak menyimpan `snapshot_id`; `stale()` membandingkannya; CLI ikut menstempel; `computing` dijawab **202**; `forget()` dipanggil saat sukses; gagal bisa diulang setelah TTL 300 detik | aditif | Tabel kebenaran `stale()` lulus; 202 untuk computing | M | `[x]` |
| 8 | `coefficients` hanya dikirim bila `normalized`; serializer memeriksa `normalized is True` | breaking (tanpa konsumen) | Set kunci `rich_club` saat `normalized:false` tidak memuat `coefficients` | S | `[x]` |
| 9 | Hapus larik `degree`/`betweenness` mentah dari `sequence.series[]` | breaking (tanpa konsumen) | `set(row) == {id, degree_rank, betweenness_rank, betweenness_rank_shift, windows_present}` | S | `[x]` |
| 11 | `pd.DataFrame(rows, columns=["entity_id", *NODE_COLUMNS])` di jalur normal | internal | Kolom sama di jalur normal dan jalur epos kosong | XS | `[x]` |
| 14 | `unstable_count` dan `truncated_degrees` = `null` saat status bukan `ready` | breaking null-vs-0 | `awaiting_input` → `None`; `ready` dengan nol → `0` | XS | `[x]` |

Dampak bundle lama: hanya `inference.json` (dihitung ulang sekali, ±72 detik
pada bundle emas) dan payload `null`. `contract_version` **tidak** naik karena
skema bundle tidak berubah.

---

## Fase D — frontend setara

| Butir | Perubahan | Kriteria terima | Effort | Status |
| --- | --- | --- | --- | --- |
| 6 | `_check_manifest()` membandingkan `channel_tolerance` dan `budget_px` (beda → exit 4). Chromium dari `--chrome` → `HORUS_CHROME` → `which` → default. Target `visual` sudah di `.PHONY` sejak Fase A | Manifest beda → exit 4; tanpa baseline → exit 4, bukan traceback | S | `[x]` |
| **4** HIGH | Gerbang label menjadi `if (isSun \|\| d.label_priority <= labelBudget())`; hapus `isAnchorNode` | Tes gagal pada kode lama, lulus pada kode baru | XS | `[x]` |
| **5** HIGH | Adapter `graphView` di `app_01.js` dengan dua implementasi (svg/canvas): `setActive`, `setQuery`, `fit`, `refresh`. Kanvas dapat `fit()` saat mount (bbox + padding 48), alpha per simpul (aktif 1, nonaktif 0,06), sisi hanya bila kedua ujung aktif. Enam pemanggil diganti | `measure_render.py` mencetak `fit_coverage ≥ 0,9` dan `dim_applied true`; 77 simpul tetap 77 `g.node-item` | L | `[x]` |
| 13 + 12 | `size_rank` menjadi opsi metrik `prominence` (default) di `SIZE_RANK_FIELDS`. Kartu sankey: tinggi = `CARD_MIN_H + (MAX-MIN) × sizeRank`, lebar tetap | Selisih > 0 antara metrik `degree` dan `prominence` di mode topik-aktor | M | `[x]` |

---

## Fase E — operasional & dokumen

| Butir | Perubahan | Kriteria terima | Effort | Status |
| --- | --- | --- | --- | --- |
| 16 | `_load()` hanya memuat 50 sesi terbaru (sisanya tetap di DB); `_evict()` tidak menghapus baris; `create_app()` selalu `configure_store` | 60 sesi → 50 di memori, 60 baris di DB | S | `[x]` |
| 15 | `add()` melaporkan tabrakan id, bukan menelan; `store_dir()` absolut dan dicatat saat start | 400 dengan pesan; `store_dir().is_absolute()` | S | `[x]` |
| 18 | `frontend_source.py` ikut `css/copilot.css`; angka disegarkan dari pengukuran ulang; rujukan `index.html:3766` → `app_07.js:67`; `tests/test_docs_consistency.py` menjaga 5–6 klaim stabil | Mengubah satu angka di dokumen membuat tes merah | S | `[x]` |

---

## Keputusan desain

Dua belas titik yang tidak bisa diputuskan oleh kode saja. Yang dipilih
ditebalkan.

| # | Keputusan | Opsi | Dipilih | Alasan |
| --- | --- | --- | --- | --- |
| D1 | Cara sanitasi SVG | **html.parser + rebuild** / ElementTree / perkuat regex | html.parser + rebuild | Parser acuan laporan adalah HTML, bukan XML; denylist selalu gagal-terbuka |
| D2 | Audit gagal | **kebijakan per kelas** / telan + log / 503 semua | kebijakan per kelas | Egress tidak boleh hilang karena disk; mutasi tak-idempoten tidak boleh terjadi tanpa jejak |
| D3 | Fallback identitas | **401 keras** / opt-out lokal / wajib token | 401 keras | Gerbang SSO berarti identitas datang dari proxy; fallback lokal membatalkan arti gerbang |
| D4 | Anggaran piksel | 120 px absolut + perbaiki dokumen / porsi 0,1% / keduanya | **perbaiki dokumen** | 120 px lebih ketat daripada 0,1% (±972 px pada 1024×950) |
| D5 | Paritas kanvas | **adapter graphView** / cabang `if` di tiap pemanggil / sembunyikan filter | adapter graphView | Enam pemanggil hari ini; cabang tersebar menghasilkan no-op baru saat ada pemanggil ketujuh |
| D6 | `size_rank` | **opsi prominence** / hapus dari payload / biarkan | opsi prominence | Menghapusnya membuang satu-satunya ringkasan komposit yang sudah diuji |
| D7 | Ukuran kartu sankey | **tinggi** / luas / kecualikan mode | tinggi | Lebar menggeser jangkar ribbon; tinggi tidak |
| D8 | Retry inferensi | **TTL 300 detik + forget** / parameter retry / hapus error saat artefak ditulis | TTL + forget | Pulih sendiri tanpa polling agresif |
| D9 | Eviksi sesi | **memori saja** / hapus DB / cap DB 500 | memori saja | Riwayat pengguna tidak boleh hilang karena batas memori |
| D10 | Token WS | **query (sekarang)** / subprotokol / cookie / tiket sekali pakai | catat batasan, tiket bila keluar loopback | WebSocket browser tidak bisa menyetel header; server default bind loopback |
| D11 | Id anotasi | **deteksi tabrakan** / 16 hex / hash penuh | deteksi tabrakan | Tanpa migrasi; tabrakan jadi terlihat, bukan diam |
| D12 | Folder anotasi | **absolut + log** / pindah ke samping bundle / wajib env | absolut + log | Opsi lain memindahkan catatan yang sudah ada |

---

## Urutan commit

| Rentang | Commit | Status | Hash |
| --- | --- | --- | --- |
| A1 | `feat(tools): pembanding tangkapan layar tanpa Pillow, gantikan shot.py` | `[x]` | `e5a96a5` |
| A2 | `build(make): target make visual untuk gerbang regresi visual` | `[x]` | `f2210df` |
| A3 | `docs: V2.2 selesai — regresi visual 3 mode x 3 lebar` | `[x]` | `113bc88` |
| B1 | `fix(export): sanitasi SVG laporan memakai allowlist, bukan denylist` | `[x]` | `041772a` |
| B2 | `fix(api): audit tidak pernah menggagalkan permintaan` | `[x]` | `606fdc1` |
| B3 | `fix(auth): identitas fail-closed saat gerbang SSO menyala` | `[x]` | `22c69ef` |
| B4 | `fix(auth): token tidak lagi lewat query string` | `[x]` | `8ddfc23` |
| C1 | `feat(api): batas laju dan audit untuk sesi serta chat` | `[x]` | `f7b8415` |
| C2 | `fix(inference): artefak terikat snapshot, job gagal bisa diulang` | `[x]` | `8615d26` |
| C3 | `fix(motifs): koefisien mentah tidak dikirim tanpa pembanding` | `[x]` | `dc8c365` |
| C4 | `refactor(sequence): seri hanya memuat peringkat` | `[x]` | `c4c89d1` |
| C5 | `fix(temporal,metrics): kolom mengikuti NODE_COLUMNS, null saat belum siap` | `[x]` | `87809a4` |
| D1 | `fix(tools): anggaran visual dibaca dari manifest, Chromium tidak hardcode` | `[x]` | `53267f1` |
| D2 | `fix(ui): label dibatasi peringkat, bukan is_anchor` | `[x]` | `de6b4cd` |
| D3 | `feat(ui): kanvas setara SVG untuk filter, cari, dan fit` | `[x]` | `591757a` |
| D4 | `feat(ui): ukuran simpul dan kartu mengikuti metrik terpilih` | `[x]` | `b45b451` |
| E1 | `fix(copilot): batas sesi ditegakkan saat muat, eviksi tidak menghapus` | `[x]` | `4ddb35e` |
| E2 | `fix(annotations): tabrakan id dilaporkan, folder absolut` | `[x]` | `25ebb52` |
| E3 | `docs: angka dan rujukan disegarkan, dijaga tes` | `[x]` | `07b89b2` |

Gerbang tiap rentang: `make check` (ruff + mypy + pytest) hijau. Baseline
542 lulus / 23 skip; **akhir 633 lulus / 23 skip**, `ruff` bersih, `mypy`
bersih atas 77 berkas. D1 dan D3 memakai `make visual` sebelum/sesudah.

Satu commit tambahan di luar tabel: `d2ce918 style(tests): urutkan blok
import` — perbaikan urutan impor yang diminta `ruff` setelah C1. Ia tidak
mengubah perilaku, jadi tidak diberi butir sendiri.

---

## Sengaja tidak dikerjakan

- Rotasi dan endpoint baca berkas audit — bukan cacat; batas V2.3 yang sudah dinyatakan.
- OIDC/JWKS — header SSO dari proxy tetap jalur yang dipilih.
- Migrasi id anotasi lama atau penulisan ulang tabel sesi — menambah risiko data tanpa manfaat.
- Mengganti kanvas ke WebGL — 2D cukup sampai ambang yang diukur.
- Dependensi baru (Pillow, bleach, lxml) — aturan repo; sanitizer memakai `html.parser` stdlib.
- Rate limit terdistribusi — satu proses, satu server; mengaku di memori sudah jujur.
- Menaikkan `contract_version` — skema bundle tidak berubah.
- Mengejar 220 fps / 30 MB — angka itu hanya perlu dikoreksi di dokumen.
- Memperbaiki 23 tes skip — penyebabnya `data/bundles/` tidak ada, kondisi lingkungan.

---

## Batasan yang tetap terbuka

| Batasan | Sebab | Penutup yang disarankan |
| --- | --- | --- |
| IDOR sesi chat | Tabel sesi tidak punya kolom pemilik; `analyst` hanya mencegah `viewer` | Tambah kolom `actor` saat `create_session`, filter saat list/hapus |
| Token di query WS | WebSocket browser tidak bisa menyetel header | Tiket sekali pakai (`POST /api/ws-ticket`, TTL 30 detik) bila server keluar dari loopback |
| Header SSO di bind non-loopback | Siapa pun yang menjangkau port bisa mengaku admin lewat header | `HORUS_TRUSTED_PROXY_IPS` dibandingkan `request.client.host` (±15 baris) |
| Laporan tidak memuat `app.css` | Sanitizer membuang `style`; laporan hanya membawa CSS template | Sertakan sub-CSS statis tepercaya atau kirim hanya layer yang terlihat |
| Cabang sankey tidak pernah tercapai | Tidak ada endpoint yang mengirim `sankey_data`; mode topik-aktor selalu jatuh ke jalur `topics`/`actors`/`edges`. Tinggi kartu sankey tetap mengikuti peringkat bila payload itu datang | Kirim `sankey_data` dari `topic_actor_network` atau hapus cabangnya |
| Kartu topik tidak ikut berskala | `/api/topics/actor-network` tidak mengirim ukuran untuk topik; hanya aktor yang punya simpul di `nodeMap` | Tambahkan `article_count`/peringkat per topik di endpoint, lalu pakai `cardHeight` yang sama |

---

## Lampiran A — 19 temuan terverifikasi

| # | Tingkat | Lokasi | Temuan |
| --- | --- | --- | --- |
| 1 | CRITICAL | `export/report.py:26-31` | Denylist SVG bocor: script tanpa penutup, `on*` tanpa spasi, `javascript:` ter-encode, `image`/`style` eksternal |
| 2 | HIGH | `api/audit.py:50-63`, `routes.py:47-55` | Kegagalan audit menaikkan `OSError` → 500 setelah state berubah |
| 3 | HIGH | `api/auth.py:129-142`, `copilot/ws.py:101` | `TRUSTED=1` tanpa header jatuh ke `local/admin`; WS tidak punya identitas |
| 4 | HIGH | `js/app_02.js:408` | `is_anchor` masih menjadi gerbang label; klaim V0.3 gugur |
| 5 | HIGH | `js/graph_canvas.js:40,56,187,229-241` | Kanvas skala 1:1 tanpa fit; filter, pencarian, tombol Fit no-op senyap di atas 2.000 simpul |
| 6 | MEDIUM | `tools/visual_regression.py:41,67`, `Makefile:10` | `BUDGET_PX` 120 absolut vs klaim 0,1%; path Chromium hardcode; `visual` tidak di `.PHONY` |
| 7 | MEDIUM | `routes.py:517`, `copilot/ws.py:58,72,186` | Rate limit hanya 2 endpoint; mutasi sesi/chat tanpa audit; delete sesi tanpa peran |
| 8 | MEDIUM | `core/motifs.py:136-141`, `api/serializers.py:99-101` | Koefisien rich-club mentah ikut dikirim; `normalized` tidak diperiksa |
| 9 | MEDIUM | `core/sequence.py:132-137` | Larik `degree`/`betweenness` mentah ikut dikirim (±5,8 KB) |
| 10 | MEDIUM | `analysis/inference.py:96-129,165`, `routes.py:193` | Artefak tanpa `snapshot_id`; `forget()` tak dipanggil; `computing` dijawab 200 |
| 11 | MEDIUM | `core/temporal.py:183,194-203` | `NODE_COLUMNS` hanya dipakai jalur epos kosong |
| 12 | MEDIUM | `js/app_08.js:174-193` | Kartu topik-aktor berukuran tetap; metrik ukuran tidak berpengaruh |
| 13 | MEDIUM | `api/encoding.py:104`, `js/app_10.js:490` | `size_rank` dikirim tapi tidak dibaca UI |
| 14 | LOW | `core/metrics/community.py:116`, `core/motifs.py:145` | `unstable_count` dan `truncated_degrees` bernilai 0 saat `awaiting_input` |
| 15 | LOW | `annotations.py:31,154` | Id 12 hex tanpa pelaporan tabrakan; folder default relatif CWD |
| 16 | LOW | `copilot/sessions.py:185-215,251-258,262-280` | Batas 50 tidak ditegakkan saat muat; eviksi menghapus baris DB; `_store` global tidak direset |
| 17 | LOW | `api/auth.py:56-59`, `js/copilot_bridge.js:13` | Token lewat query string di HTTP dan URL WS |
| 18 | LOW | `docs/planning/IMPROVEMENTS.md` | Angka usang: 112 vs 98 baris, 918 vs 909, 542 vs 535 tes, mypy 76 vs 70, 220 fps/30 MB vs 247 fps/22 MB, rujukan mati |
| 19 | MEDIUM | working tree | Pekerjaan V2.2 belum di-commit (ditutup di Fase A) |

# Fase V — dari demo ke kelas enterprise

Lanjutan [`ROADMAP.md`](ROADMAP.md). Fase 0–3 menutup integritas, performa, UX,
dan lapisan server; fase V menutup jarak antara "aplikasi yang benar" dan "alat
yang temuannya bisa dikutip lembaga lain".

Ruang lingkup: **hanya kode di repo ini**. Bundle dan crawler di luar cakupan —
kalau sebuah butir menuntut perubahan bentuk data, itu ditulis eksplisit sebagai
perubahan kontrak, bukan diasumsikan.

Legenda effort: **XS** < 1 jam, **S** setengah hari, **M** satu-dua hari,
**L** lebih dari dua hari.

---

## Diagnosis yang jadi dasar urutan

Empat angka, semuanya terukur di repo ini:

| Temuan | Bukti |
| --- | --- |
| Encoding visual dikalibrasi ke satu dataset | `index.html:3778-3781` memakai `(deg-11)/(47-11)`, `bw/0.04`, volume `2.2–3.85`; `:6425-6437` memakai `/60`, `/0.08`, `/35` |
| Dua rumus radius untuk variabel yang sama | `assignNodeProminence` (`:3766`) vs `computeNodeRadius` (`:6419`) |
| Rigor statistika tidak sampai ke produk | `api/routes.py:106` memanggil `reporting_block` tanpa `null`/`bootstrap`; `enhance/reporting.py:68` hanya menambah `inference` bila objeknya sudah dihitung |
| Seluruh graf dikirim sekali | `/api/bootstrap` 155 KB untuk 77 simpul (`serializers.py:31`) |

Konsekuensinya: dataset kedua akan tampil "benar" tapi salah — semua simpul
jatuh ke tier bawah, tanpa error. Itu kegagalan yang lebih mahal daripada crash,
karena tidak ada yang tahu harus curiga.

---

## Keputusan arsitektur

Tiga keputusan yang mengikat sisa dokumen ini. Kalau salah satu dibalik, butir
turunannya ikut berubah.

**1. Skala visual dihitung di Python, bukan di JS.**
Alasan: engine sudah punya data, tes, dan disiplin "satu aturan" (`_coerce.py`,
`stance.py`). Menaruh aturan skala di JS berarti aturan itu tidak bisa diuji
tanpa harness JS baru, dan akan bercabang lagi seperti `:3766` vs `:6419`.
Yang dikirim: `size_rank` (0–1), `radius_tier` (1–5), `label_priority` (int).
Alternatif yang ditolak: pustaka skala di JS (d3.scaleQuantile) — benar secara
matematis, tapi menambah tempat kedua yang bisa lupa diperbarui.

**2. Ambang backbone jadi data, default tetap.**
`manifest.backbone` opsional (`min_support`, `min_npmi`, `rescue_isolated`).
Tanpa blok itu, perilaku hari ini tidak berubah. Ini menaikkan kontrak ke
**1.2.0** (minor, aditif) — bukan 2.0, karena bundle 1.0/1.1 tetap sah.
Alternatif yang ditolak: ambang sebagai argumen `serve` saja. Itu memindahkan
masalah ke operator dan tidak ikut tersimpan bersama snapshot.

**3. View state hidup di URL dulu, tanpa endpoint baru.**
`#v=1&m=…&t=…&y=…&f=…&z=…&s=…`, divalidasi per-field, field tak dikenal
diabaikan. Temuan jadi bisa dikutip sebagai tautan. Penyimpanan sisi server
(siapapun bisa membuka "kasus") ditunda ke V2.3 karena butuh identitas pengguna
lebih dulu — tanpa itu, "view tersimpan" hanya global dan tidak bisa dipercaya.

---

## Fase V0 — Kejujuran visual

Tujuan: satu dataset baru tidak boleh menghasilkan gambar yang menyesatkan, dan
tampilan yang sama harus bisa dibuka ulang persis. Semua butir V0 murah; tidak
ada alasan menundanya.

- [x] **V0.1 Skala visual dihitung engine** — M
  - Berkas: `api/serializers.py:74` (`node_payloads`), `index.html:3766`,
    `:6419`
  - Kerjakan: tambah blok per simpul `size_rank`, `radius_tier`,
    `label_priority` yang dihitung dari **peringkat persentil** degree, artikel,
    dan betweenness — bukan dari batas tetap. Bobot komposit tetap
    (0.45/0.35/0.20) karena itu pilihan presentasi, tetapi pemetaannya jadi
    invarian terhadap ukuran dan bentuk distribusi. Tier dibentuk dari kuantil
    peringkat, dan seri diputus oleh `entity_id`, sehingga kelima tier terisi
    untuk setiap graf dengan ≥ 5 simpul.
  - Terima: untuk bundle 77 simpul, kelima tier terisi; untuk bundle sintetis 6
    simpul, kelima tier juga terisi. Tidak ada angka mentah dataset di
    `index.html` (`grep -n "47 - 11\|/ 0.04\|3.85"` kosong).
  - Tes: `tests/test_api.py` — setiap simpul punya `radius_tier` di 1..5;
    `size_rank` monoton terhadap degree pada graf bintang; bundle 5 simpul
    menghasilkan 5 tier berbeda.
  - Effort alasan: satu fungsi + satu blok payload + satu jalur UI.
  - Hasil: `horus_graph/api/encoding.py` (98 baris) menghitung
    `size_rank`, `rank_degree`, `rank_volume`, `rank_betweenness`, `rank_burt`,
    `radius_tier`, `label_priority` dari peringkat persentil; seri diputus
    `entity_id`. `node_payloads` memanggilnya sekali per graf lewat
    `_attach_size_encoding`. Diukur di browser: 77 simpul → **77 radius
    berbeda**, rentang 6–28 (dulu hanya lima nilai: 28/22/15/9.5/6). Tes:
    `tests/test_api_encoding.py` (11 kasus, termasuk tier penuh untuk 5/6/17/77/400
    simpul dan metrik kosong yang ditaruh di belakang).

- [x] **V0.2 Satu radius untuk semua mode** — S
  - Berkas: `index.html:3766`, `:6419`, `:6440`
  - Kerjakan: hapus `assignNodeProminence`; `computeNodeRadius` membaca
    `radius_tier` dari payload. Pemilih metrik ukuran (`degree`/`betweenness`/
    `burt`/`volume`) tetap ada, tetapi memilih **peringkat** yang mana, bukan
    menghitung ulang skala.
  - Terima: simpul yang sama punya radius identik di mode aktor, topik-aktor,
    dan setelah memilih metrik ukuran yang sama. Satu fungsi radius tersisa di
    berkas.
  - Tes: `tests/test_frontend_integrity.py` — `assignNodeProminence` tidak ada;
    `computeNodeRadius` hanya membaca field payload, tidak ada literal pembagi.
  - Hasil: `assignNodeProminence` dan `getNodeRadius` dihapus (34 baris);
    `computeNodeRadius` kini `RADIUS_MIN + (RADIUS_MAX - RADIUS_MIN) * rank`,
    dengan `SIZE_RANK_FIELDS` memetakan lima pilihan metrik ke lima field
    peringkat. Radius tidak lagi bergantung pada metrik mentah, jadi simpul yang
    sama tampil sama besar di semua mode. Diukur: `assignNodeProminence` →
    `undefined` di runtime.

- [x] **V0.3 Label dari peringkat, bukan dari anchor** — S
  - Berkas: `index.html` (tempat label digambar), `serializers.py:102`
    (`is_anchor`)
  - Kerjakan: tampilkan label untuk `label_priority` teratas (batas tetap,
    mis. 40) + simpul terpilih + hover. `is_anchor` tetap dipakai sebagai
    penanda, bukan sebagai penentu label.
  - Terima: pada bundle 1.000 simpul sintetis, jumlah label di layar ≤ 60;
    label tidak pernah bertumpuk satu sama lain pada zoom awal.
  - Tes: penghitung label di DOM lewat harness Chromium headless yang sudah
    dipakai Fase 2.
  - Hasil: `labelBudget()` = `min(40, max(8, ceil(0.15 × jumlah simpul)))`;
    `applyLabelBudget()` menyembunyikan label yang bertabrakan, dihitung ulang
    saat simulasi berhenti dan saat zoom berakhir. Diukur pada bundle 77
    simpul: 20 label dibuat, **12 tampil, 8 disembunyikan** karena bertumpuk.
    Label anchor dari data tetap muncul; `is_anchor` tidak lagi menentukan
    apakah sebuah simpul diberi label.

- [x] **V0.4 View state di URL** — M
  - Berkas: `index.html` (inisialisasi + semua setter mode/filter/zoom),
    `js/copilot_bridge.js` (jangan sentuh token)
  - Kerjakan: serialisasi `mode`, topik, epos, filter tipe, kamera, dan simpul
    terpilih ke `location.hash`; pulihkan saat muat; tombol "salin tautan".
    Validasi per-field: nilai di luar enum diabaikan, bukan dilempar. Token
    tetap di `sessionStorage` dan tidak pernah masuk URL.
  - Terima: muat ulang halaman memulihkan mode, filter, epos, kamera, dan
    seleksi. Hash rusak (`#v=1&m=hantu`) menghasilkan tampilan default tanpa
    error di konsol. Tautan tanpa `?token=` tetap bisa dibuka bila token sudah
    ada di `sessionStorage`.
  - Tes: `tests/test_frontend_integrity.py` — parser menolak field asing;
    `grep` memastikan token tidak pernah ditulis ke `location.hash`.
  - Hasil: `#v=1&m=&t=&c=&k=&w=&n=&y=&s=&z=` diserialisasi otomatis (satu
    listener `click/change/keyup` + zoom end), dipulihkan setelah tata letak
    berhenti lewat `flushViewState()`. Tiga kali muat ulang berturut-turut
    memulihkan mode `topic_actor`, ukuran `degree`, simpul terpilih, dan kamera
    `k=1.4` — sama persis. Hash rusak diabaikan per-field (whitelist enum),
    token tidak pernah masuk hash, dan skrip token di kepala halaman sekarang
    mempertahankan hash saat membersihkan `?token=`.
  - Sisa yang sengaja tidak dikerjakan: **tombol "salin tautan"** tidak dibuat.
    Header sudah diukur 0 px luber di Fase 2, dan hash diperbarui otomatis
    sehingga tautan bisa disalin dari address bar. Bila tombol tetap diinginkan,
    tempatnya di menu "Data", bukan di toolbar.
  - Catatan temuan: `applyTimelineFilter` masih menulis `epoch_1..epoch_3`
    sebagai literal (`index.html:3529-3532`). Tidak merusak bundle lain karena
    `updatePillsState` mengabaikan kunci tak dikenal, tetapi itu asumsi dataset
    yang tersisa — kandidat butir berikutnya.

**Selesai V0 bila:** dataset sintetis dengan 6 simpul dan 1.000 simpul
menghasilkan gambar yang masuk akal tanpa menyunting kode, dan sebuah tampilan
bisa dibuka ulang dari satu tautan.

Status: **selesai** — keempat butir tertutup, 328 tes lulus, `ruff` dan `mypy`
bersih. Diukur di Chromium headless: 77 radius berbeda (6–28), 12 dari 20 label
tampil, dan tautan memulihkan mode + ukuran + seleksi + kamera secara konsisten
tiga kali berturut-turut.

---

## Fase V1 — Temuan yang bisa dikutip

Tujuan: setiap angka di layar bisa dipertahankan saat ditanya "dari mana, dan
seberapa yakin?". V1 bergantung pada V0.4 (tautan) dan V0.1 (peringkat).

- [x] **V1.1 Ambang jadi data + panel sensitivitas** — L
  - Berkas: `contract/models.py` (blok `backbone`), `core/backbone.py:25`,
    `api/state.py:84`, `api/serializers.py:31`, `index.html`
  - Kerjakan: (a) `manifest.backbone` opsional, kontrak 1.2.0, dibaca
    `build_network` bila tidak ada `BackboneConfig` eksplisit; (b) endpoint
    `GET /api/analysis/sensitivity` yang hanya menjalankan pemilihan backbone
    (bukan metrik penuh) pada ~12 titik ambang dan mengembalikan kurva
    jumlah sisi/simpul — ini murah, karena sentralitas tidak dihitung ulang;
    (c) panel di UI menampilkan kurva itu + penanda posisi ambang aktif, dan
    satu tombol "pakai ambang ini" yang memuat ulang bootstrap dengan parameter
    tersebut (cache per `snapshot_id` + parameter, `maxsize=2`).
  - Terima: panel menampilkan kurva dalam < 2 detik pada bundle 77 simpul;
    memilih ambang berbeda mengubah jumlah sisi dan angka itu tidak pernah
    tertinggal dari kanvas; `manifest.backbone` yang tidak ada menghasilkan
    perilaku identik dengan hari ini.
  - Tes: `tests/test_core_backbone.py` — blok manifest dipakai; override
    eksplisit menang. `tests/test_api.py` — kurva monoton, titik ambang aktif
    ada di dalam kurva.

  **Status: selesai sebagian — (a) dan (b) ditutup, (c) ditutup tanpa tombol.**

  - (a) `BackboneSettings` di `contract/models.py`, `manifest.backbone`
    opsional, kontrak 1.2.0 (aditif; validasi hanya memeriksa versi mayor,
    jadi bundle 1.1.0 tetap dimuat). `core/build.py::backbone_config()` menjadi
    satu-satunya pembaca blok itu. CLI `build` ikut diperbaiki: `--min-support`
    dan `--min-npmi` kini berdefault `None`, sehingga ambang milik bundle
    dipakai bila flag tidak diberikan. Sebelum ini default argparse (3 / 0.2)
    selalu menimpa data — blok manifest tidak akan pernah berpengaruh lewat CLI.
  - (b) `analysis/sensitivity.py` + `GET /api/analysis/sensitivity?points=`.
    Hanya `select_edges` yang dijalankan; sentralitas dan komunitas tidak
    dihitung ulang.
  - (c) Panel ada di modal Network Overview dengan dua kurva dan penanda
    "aktif". **Tombol "pakai ambang ini" sengaja tidak dibuat** — lihat catatan
    di bawah.

  **Dua koreksi yang muncul saat mengerjakan, keduanya karena data nyata:**

  1. Batas atas ambang yang tetap (20) membuat kurva support pada bundle golden
     **seluruhnya datar**: support di sana mencapai 9039, jadi sapuan 1..20
     tidak pernah menyentuh titik di mana sisi mulai gugur. Panel akan
     melaporkan "tidak sensitif" padahal hanya tidak terjangkau. Grid sekarang
     diambil dari kuartil sebaran nilai yang benar-benar ada, ditambah nilai
     aktif, sehingga batas keruntuhan selalu ikut. Diuji oleh
     `test_kurva_bundle_nyata_tidak_datar`.
  2. `edges` (total) **tidak monoton**: makin tinggi ambang, makin banyak simpul
     kehilangan seluruh sisinya, dan `rescue_isolated` menambahkan kembali sisi
     terkuat masing-masing. Kurva yang naik-turun terbaca seperti salah hitung.
     Karena itu `passed` dan `rescued` dipisah, dan panel menggambar dua garis:
     penuh untuk `passed` (monoton), putus-putus untuk `edges`.

  **Kenapa tombol "pakai ambang ini" tidak dibuat.** Tombol itu menuntut
  `/api/bootstrap` membangun ulang jaringan per parameter. Itu bertabrakan
  dengan keputusan arsitektur yang sudah mengikat di dokumen ini: **satu
  `AppState` per proses**, supaya angka antar panel tidak mungkin berasal dari
  dua proses build berbeda. Membangun ulang per permintaan juga menyeret
  `temporal`, `bipartite`, dan `anomaly` yang tidak bergantung pada ambang, lalu
  membuka pertanyaan koherensi baru: id simpul berubah, tautan `#v=1` menyimpan
  pilihan yang mungkin sudah tidak ada, dan anotasi per `snapshot_id` menjadi
  tidak berlaku. Jalur yang didukung untuk mengubah ambang secara permanen
  sudah ada dan sekarang benar: isi `manifest.backbone`, atau jalankan
  `horus-graph build <bundle> --min-support N` untuk melihat hasilnya.

  Yang tetap diberikan panel: kurva itu sendiri, penanda posisi ambang aktif,
  dan kalimat "pada support 3: 475 sisi (467 lolos, 8 diselamatkan)". Pembaca
  bisa melihat akibat pergeseran ambang tanpa kanvas ikut berubah di bawah
  tangannya.

- [x] **V1.2 Inferensi sampai ke layar** — M
  - Berkas: `api/routes.py:106`, `enhance/reporting.py:68`, `index.html`
  - Kerjakan: endpoint `GET /api/inference` yang menghitung null model dan
    bootstrap dengan seed tetap lalu menyimpannya di cache proses per
    `snapshot_id`; `/api/provenance` tetap murah dan tidak ikut menghitung.
    UI menampilkan p-value beserta resolusinya (`1/(resamples+1)`) dan CI
    sebagai rentang, bukan angka tunggal.
  - Terima: pada bundle golden, p-value modularitas muncul dengan keterangan
    resolusi; tidak pernah tampil `p = 0`; membuka panel dua kali tidak
    menghitung ulang (waktu respons kedua < 100 ms).
  - Tes: `tests/test_api.py` — `/api/inference` mengembalikan `null_model` dan
    `bootstrap`; p-value ≥ resolusi; panggilan kedua tidak menaikkan hitungan
    komputasi (dihitung lewat spy).

  **Status: selesai — dengan satu perubahan rencana.**

  Biayanya diukur lebih dulu, dan angkanya mengubah desain: pada bundle golden,
  200 resampling null model memakan **50 detik** dan bootstrap artikel **22
  detik**. Endpoint yang menghitung di dalam handler berarti satu permintaan
  menggantung lebih dari satu menit — gagal pada kriteria "respons kedua < 100
  ms", dan lebih buruk lagi karena UI tidak bisa membedakan "sedang dihitung"
  dari "macet".

  Jadi inferensi diperlakukan sebagai artefak, bukan kerja per permintaan:

  1. `horus-graph inference <bundle> --write` menghitung di luar server dan
     menulis `<bundle>/inference.json` (tulis atomik: `.tmp` lalu `replace`).
  2. `GET /api/inference` membaca artefak itu bila ada dan masih cocok dengan
     parameternya → `source: "artifact"`, ~10 ms.
  3. Bila tidak ada, permintaan **tidak** menghitung: ia memulai satu thread
     latar (`InferenceJobs`, satu per `snapshot_id`) dan menjawab **202**
     `status: "computing"`. UI memantau tiap 3 detik, paling banyak 40 kali,
     dan berhenti saat panel ditutup.
  4. Hasil di memori dipakai lebih dulu daripada menghitung ulang; kegagalan
     menulis artefak (bundle di mount read-only) tidak menggagalkan permintaan.

  **Bug integritas yang ikut diperbaiki.** `degree_preserving_null` mengembalikan
  `p_value = 1.0` untuk semua metrik ketika tidak ada resample yang berhasil.
  Itu angka hasil uji pada situasi yang tidak punya uji: pembaca melihat "sudah
  diuji, tidak signifikan" padahal metriknya tidak terukur. Sekarang `None`,
  dan `_p_value` mengembalikan `None` juga bila observasinya tidak terdefinisi
  (`empirical_p_value` sengaja tetap 1.0 di lapisan statistik, karena di sana
  ia dipakai untuk membandingkan, bukan untuk dilaporkan). `seed` yang diminta
  juga diteruskan apa adanya, bukan diganti 0.

  **Bug frontend yang tertangkap saat verifikasi visual.** Panel pertama kali
  ditulis dengan `const null = block.null_model || {}`. `null` kata kunci, jadi
  seluruh blok `<script>` gagal di-parse; halaman tetap tampil (markup statis)
  tetapi tidak ada data yang dimuat, tanpa satu pun pesan di UI. Diperbaiki,
  lalu ditutup dengan pagar baru di `tests/test_frontend_integrity.py`:
  `test_tidak_ada_kata_kunci_dipakai_sebagai_nama_variabel`.

  Hasil pada bundle golden (seed 42, 200 resample): modularitas Q 0.3872
  (z 27.58, p ≤ 0.010), transitivity 0.7352 (z 62.45, p ≤ 0.010),
  assortativity 0.2255 (z 6.75, p ≤ 0.010), ARI komunitas 0.9156
  (p05–p95 0.8044–1.0000). Panel menuliskan resolusi 1/(200+1) = 0.0050 dan
  batas dua sisi 0.010, jadi `p ≤ 0.010` terbaca sebagai batas resolusi, bukan
  sebagai nol.

- [x] **V1.3 Diff epos yang sungguhan** — M
  - Berkas: `api/queries.py` (`graph_compare`), `api/routes.py:…`
    (`/api/graph/compare`), `index.html:7236`
  - Kerjakan: perluas respons dengan delta per simpul (`degree`, `betweenness`,
    `community`) dan sisi masuk/keluar; UI menampilkan tabel berperingkat
    `|Δbetweenness|` di samping cincin kanvas yang sudah ada. Cincin tetap,
    karena itu penanda lokasi; tabel yang menjawab "siapa naik".
  - Terima: memilih dua epos menampilkan 10 gainer dan 10 loser dengan angka
    yang bisa dihitung ulang dari `/api/temporal`; simpul yang tidak ada di
    salah satu epos muncul sebagai `baru`/`hilang`, bukan `Δ 0`.
  - Tes: `tests/test_api.py` — delta konsisten dengan dua potret temporal;
    simpul baru tidak menghasilkan delta numerik.

  **Status: selesai — dengan satu koreksi pada rencana.**

  Rencana menulis "delta `community`". Itu tidak bisa dikerjakan apa adanya:
  label komunitas Louvain ditulis ulang setiap jalankan, jadi `2 - 1 = 1`
  hanya berarti algoritma memulai dari titik lain. Yang dikerjakan:

  - Setiap simpul membawa `baseline_community`, `target_community`, dan
    `community_shifted`. Perpindahan ditentukan lewat pemetaan label baseline
    ke label target berdasarkan tumpang tindih terbesar, bukan kesamaan angka.
  - `community_agreement` (ARI antara dua partisi pada simpul yang bertahan)
    meringkas "apakah struktur komunitas berubah" tanpa bergantung penomoran.
  - Respons memuat `community_map` sehingga UI bisa menjelaskan kasus yang
    membingungkan: simpul `1 → 1` tetap bisa berstatus "pindah" bila mayoritas
    komunitas 1 berakhir di komunitas lain. Tooltip-nya menyebut tujuan
    mayoritas itu, karena tanpa keterangan baris seperti itu terbaca salah.

  **Sisi, bukan hanya simpul.** `edges_gained`/`edges_lost` berisi pasangan
  yang lahir dan mati, lengkap dengan `support` dan `npmi` dari epos tempat sisi
  itu hidup, diurutkan menurut support dan dibatasi 10. Pasangan dianggap sama
  tanpa memandang arah, karena grafnya tak berarah.

  **UI.** Tombol "Bandingkan" kini juga membuka modal `Diff Epos` berisi dua
  tabel berperingkat (10 naik, 10 turun) dan daftar sisi baru/hilang. Cincin di
  kanvas tetap ada — itu penanda lokasi; tabel yang menjawab "siapa naik".
  Tombol "Lihat Diff" membuka ulang tabel terakhir tanpa memanggil ulang API,
  dan tidak membuka apa pun bila belum ada perbandingan (panel kosong terbaca
  seperti "tidak ada yang berubah").

  **Bug yang ditemukan saat mengerjakan.** `core/temporal.py::_node_metrics`
  ternyata **tidak pernah menghitung komunitas per epos**, dan jalur epos-kosong
  mendeklarasikan daftar kolom yang berbeda dari jalur normal. Akibatnya
  permintaan kolom komunitas gagal dengan `KeyError` hanya ketika salah satu
  epos kebetulan kosong — kegagalan yang bergantung pada data, bukan pada kode.
  Sekarang ada satu konstanta `NODE_COLUMNS` yang dipakai kedua jalur, dan
  komunitas dihitung per irisan.

  Angka pada bundle golden (epoch_1 → epoch_3): 11 masuk, 5 keluar, 58 bertahan,
  ARI komunitas 0.2653 (20 simpul berpindah), 10 sisi baru, 10 sisi hilang.
  Puncak kenaikan: Reva Adi Utama Δbetweenness +0.0625 (degree 10 → 20).
  Puncak penurunan: RANS Nusantara FC −0.0913 (degree 23 → 3).

- [ ] **V1.4 Anotasi + laporan mandiri** — L
  - Berkas: baru `horus_graph/annotations.py`, `api/routes.py`, `index.html`
  - Kerjakan: catatan per simpul/sisi disimpan per `snapshot_id` di luar folder
    bundle (`data/annotations/<snapshot_id>.json`, tulis atomik). Ekspor
    laporan: satu berkas HTML mandiri berisi SVG kanvas saat ini, daftar
    anotasi, blok provenance (ambang, seed, `snapshot_id`, `limitations`), dan
    tabel angka yang dikutip. Tanpa dependensi baru.
  - Terima: laporan dibuka offline tanpa server dan tetap memuat
    `snapshot_id`, ambang, serta seluruh `limitations`; anotasi bertahan setelah
    server restart; menghapus anotasi tidak menyentuh berkas bundle.
  - Tes: `tests/test_annotations.py` — tulis/baca/hapus; idempoten. Ekspor
    diuji dengan membaca HTML hasil dan mencari `snapshot_id` + `limitations`.

**Selesai V1 bila:** satu temuan bisa diserahkan sebagai tautan + laporan HTML
yang memuat ambang, ketidakpastian, dan batasannya — tanpa menjelaskan apa pun
secara lisan.

---

## Fase V2 — Skala dan arsitektur

Tujuan: bertahan pada dataset tingkat nasional dan pada lebih dari satu
pengguna. Ini fase termahal; jangan mulai sebelum V0 selesai, karena V2.1
memindahkan renderer yang isinya masih akan berubah di V0–V1.

- [ ] **V2.1 Renderer canvas/WebGL + LOD** — L
  - Berkas: `index.html` (lapisan render), baru `web/static/js/render.js`
  - Kerjakan: gambar simpul/sisi ke canvas (2D cukup sampai ~20 ribu sisi;
    WebGL hanya bila terbukti perlu). Level-of-detail: label dan panah hanya
    saat zoom melewati ambang. Layout dihitung sekali lalu disimpan, supaya
    muat ulang tidak menjalankan simulasi lagi.
  - Terima: bundle sintetis 10.000 simpul / 50.000 sisi tampil < 2 detik dan
    pan/zoom ≥ 30 fps di mesin pengembangan; memori halaman < 500 MB.
  - Tes: `tests/fixtures/synthetic_scale.py` (deterministik) + skrip Chromium
    headless yang mengukur waktu paint dan frame.

- [ ] **V2.2 Pecah frontend + regresi visual** — L
  - Berkas: `index.html` (7.792 baris), `web/static/js/*`
  - Kerjakan: pisahkan menjadi modul ES tanpa bundler (native import) — render,
    state, filter, panel, laporan. Pertahankan satu berkas HTML sebagai shell.
    Tambah tangkapan layar headless untuk 3 mode × 3 lebar sebagai pembanding.
  - Terima: tidak ada berkas JS > 800 baris; `index.html` < 1.500 baris;
    tangkapan layar identik dengan toleransi piksel yang dinyatakan.
  - Tes: skrip regresi visual dijalankan lokal dan di CI (opsional di CI karena
    butuh Chromium).

- [ ] **V2.3 Identitas, audit, dan sesi persisten** — L
  - Berkas: `api/auth.py`, `copilot/sessions.py:42`, `api/app.py`
  - Kerjakan: OIDC/OAuth2 (atau header SSO dari reverse proxy) → peran
    `viewer`/`analyst`/`admin`; log audit tindakan (siapa, kapan, snapshot,
    aksi: buka view, ekspor, hapus anotasi) ke berkas append-only; sesi chat
    pindah dari `dict` ke SQLite; rate limit per token.
  - Terima: restart server tidak menghilangkan sesi; setiap ekspor tercatat
    dengan identitas pemanggil; `viewer` tidak bisa menghapus anotasi (403);
    tanpa identitas, perilaku hari ini (token tunggal) tetap jalan.
  - Tes: `tests/test_auth.py` — matriks peran; `tests/test_sessions.py` —
    persistensi lintas instance.

- [ ] **V2.4 SNA tambahan** — L
  - Berkas: `core/metrics/community.py`, baru `core/diffusion.py`,
    `core/motifs.py`, `api/queries.py`
  - Kerjakan, berurutan sesuai nilai: (a) consensus clustering lewat matriks
    co-asosiasi dari banyak jalankan Louvain — tanpa dependensi baru, langsung
    memberi angka stabilitas per simpul; (b) triad census + rich-club
    (`networkx` sudah menyediakan keduanya); (c) simulasi difusi independent
    cascade + threshold (numpy murni); (d) graph sequence per jendela waktu
    dengan sentralitas dinamis. Leiden/Infomap hanya bila (a) terbukti kurang —
    keduanya menambah dependensi (`igraph`), dan aturan repo melarang menambah
    permukaan tanpa alasan yang terukur.
  - Terima: setiap metrik baru muncul di `/api/bootstrap` **hanya** bila
    dihitung, dengan status `awaiting_input` bila tidak; angka stabilitas
    komunitas bisa dibaca per simpul; difusi menerima seed dan jumlah simulasi
    dan mengembalikan distribusi, bukan satu angka.
  - Tes: satu tes per metrik dengan graf kecil yang jawabannya bisa dihitung
    tangan; difusi deterministik pada seed tetap.

**Selesai V2 bila:** satu bundle 10 ribu simpul terbuka dalam 2 detik, dua
pengguna dengan peran berbeda bisa bekerja tanpa saling menimpa, dan setiap
tindakan yang mengubah temuan tercatat.

---

## Sengaja tidak dikerjakan

| Item | Alasan |
| --- | --- |
| ERGM / SAOM / model ruang laten | Butuh R (`statnet`, `RSiena`). Jalur yang benar: ekspor GraphML (sudah ada) lalu analisis di R. Memaksakannya ke Python berarti memelihara estimasi MCMC sendiri |
| Graf 3D | Tidak ada pertanyaan analitis yang dijawab lebih baik oleh dimensi ketiga; biaya persepsi dan implementasi tinggi |
| Kolaborasi real-time | Belum ada dua pengguna simultan; konflik penyuntingan lebih mahal daripada manfaatnya |
| Multi-tenancy penuh | Fork = ganti bundle (keputusan Fase 0). Registry read-only cukup |
| Narasi otomatis sebagai default | Copilot sudah punya jalur deterministik; membiarkan model mengarang kalimat sebagai default membatalkan seluruh kerja integritas |
| Pustaka chart pihak ketiga (Plotly/ECharts) | Satu-satunya alasan memakainya adalah kecepatan render; V2.1 menyelesaikannya tanpa kehilangan kendali atas encoding |
| Tombol "pakai ambang ini" (V1.1c) | Menuntut `/api/bootstrap` membangun ulang jaringan per parameter, yang membatalkan keputusan "satu `AppState` per proses" dan membuka ketidakkonsistenan id simpul, tautan `#v=1`, serta anotasi per `snapshot_id`. Jalur permanen sudah ada: `manifest.backbone` atau `build --min-support` |

---

## Urutan dan ketergantungan

```
V0.1 ── V0.2 ── V0.3
  └──── V0.4 ──────────────┐
                            ├── V1.2 ── V1.3
V1.1 (mandiri) ─────────────┘
V1.4 (butuh V0.4)

V2.1 (butuh V0.1–V0.3)  V2.2 (butuh V2.1)  V2.3 (mandiri)  V2.4 (mandiri)
```

Aturan yang dipakai:

1. V0 sebelum V1: angka yang salah skalanya tidak layak diberi panel inferensi.
2. V1.1 sebelum dataset baru: tanpa itu, dataset kecil akan tampak "rusak" dan
   waktu habis untuk mendiagnosis ambang, bukan data.
3. V2.1 sebelum V2.2: memecah berkas sebelum renderer diganti berarti
   memecahkan kode yang sebentar lagi dibuang.
4. Satu fase, satu rentang commit — sama seperti aturan di `README.md`.

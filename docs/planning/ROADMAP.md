# Roadmap

Empat fase, dikerjakan berurutan. Alasan tiap butir ada di [`AUDIT.md`](AUDIT.md).
Coret butir saat selesai; jangan hapus.

Legenda effort: **XS** < 1 jam, **S** setengah hari, **M** satu-dua hari,
**L** lebih dari dua hari.

---

## Fase 0 — Integritas

Tujuan: tidak ada satu angka pun di layar yang tampil tanpa dasar data. Fase
ini kecil tapi menjadi syarat semua fase lain.

- [x] **0.1 Sentimen berhenti dikarang** — M
  - Berkas: `api/serializers.py:62` (`node_payloads` tidak punya field sentimen), `index.html:4102-4104`, `:4381-4383`, `:5987`, `js/copilot_bridge.js:81`
  - Kerjakan: kirim blok `sentiment {status, pos, neu, neg, stance}` per simpul **hanya** bila `network.sentiment` ada. UI bercabang pada `dataset.layers.sentiment`, bukan pada keberadaan field: bila `awaiting_input`, render label `awaiting_layer` dan sembunyikan bar serta stance. Perbaiki tiga konsumen lain yang membaca `m.sentiment_*` padahal API tidak pernah mengirimnya, dan `copilot_bridge.js` yang membaca `d.sentiment_pos` padahal dossier mengirim `d.sentiment.pos`.
  - Terima: pada bundle tanpa lapisan sentimen, tidak ada persentase maupun stance di mana pun. `grep -n "sentiment_pos" index.html` tidak lagi memuat fallback numerik.
  - Tes: `tests/test_api.py` cek `network.sentiment is None` → node payload tidak memuat `sentiment`; bila ada, `sentiment.status == "ready"`.

- [x] **0.2 Panel bukti tepi hidup** — S
  - Berkas: `index.html:4219` (path), `:4220` (penelan 404), `:4224-4251` (nama field)
  - Kerjakan: ubah ke `/api/edges/evidence`; ganti `evidence_snippets` → `evidence`; hapus pembacaan `salton_cosine`/`jaccard` yang tidak dikirim route **atau** tambahkan keduanya ke `queries.shared_articles`; petakan `site`/`published_at` ke label UI; hapus `res.ok ? ... : null` dan tampilkan pesan error.
  - Terima: klik satu sisi di kanvas menampilkan daftar judul artikel nyata dan jumlah cuplikan > 0. Bila route gagal, panel menampilkan pesan gagal, bukan diam.
  - Tes: `tests/test_api.py` menguji `/api/edges/evidence` mengembalikan `evidence[].title` dan `site`.

- [x] **0.3 Hapus default yang terbaca sebagai data** — XS
  - Berkas: `index.html:2755` (`CRITICAL`), `:2757` (`high_brokerage_entity`), `:2722` (`+0.28`)
  - Kerjakan: ganti dengan `—` dan kelas netral; isi hanya setelah simpul dipilih.
  - Terima: sebelum memilih simpul, panel kanan tidak menampilkan kata `CRITICAL`, `high_brokerage_entity`, atau angka apa pun.

- [x] **0.4 Nama model dari manifest** — XS
  - Berkas: `index.html:2437`
  - Kerjakan: ambil dari `BOOTSTRAP.dataset.generator` / `provenance`, atau hapus barisnya bila manifest tidak menyediakan.
  - Terima: `grep -rn "NusaBert" horus_graph/` kosong.

- [x] **0.5 Pagar integritas** — S
  - Kerjakan: satu tes yang memastikan tidak ada literal numerik sebagai fallback pada panel status (sentimen, stance, prioritas, peran). Pendekatan: grep terarah di `index.html` untuk pola `!== undefined ? .* : <angka>`.
  - Terima: tes gagal bila ada penambahan baru dengan pola itu.
  - Hasil: `tests/test_frontend_integrity.py` (9 tes). Isinya: ternary berangka
    dilarang, `|| <angka>` dilarang pada baris yang menulis ke layar, lima
    literal markup karangan dilarang, sentimen hanya dibaca lewat
    `nodeSentiment()`, dan status lapisan hanya dibaca dari `dataset.layers`.
    Regresi yang disuntikkan sengaja (`m.pagerank !== undefined ? ... : 0.0150`)
    memang menggagalkan tes.

**Selesai fase 0 bila:** kelima butir hijau, 221+ tes lulus, dan tidak ada
angka di layar yang tidak berasal dari `AppState`.

Status: **selesai** — 233 tes lulus. Tinjauan kode sebelum commit menemukan
satu cacat yang lolos dari tes: `Number(null) === 0`, sehingga baris sentimen
berkolom kosong akan tampil sebagai `Pos 0% / Neu 0%`. Ditutup dengan menolak
null sebelum `Number()` dan tidak mengirim blok sama sekali bila salah satu
dari pos/neu/neg kosong; diuji di `test_baris_sentimen_bolong_tidak_menjadi_nol`. Selain lima butir di atas, penyisiran teks
markup menemukan empat kebocoran lain yang ikut ditutup: `Neg 20%` di kartu
hover, legenda "Sentimen Sisi (Signed SNA)" yang mencantumkan valensi rekaan
per kategori (diganti legenda "Kategori Sisi" yang dibentuk dari kategori nyata
dan warna kanvas), `13.789 artikel` di tooltip, dan `545 Edges`. Pilihan epos
pada bilah komparasi juga tidak lagi ditulis mati sebagai `epoch_1..3`.

---

## Fase 1 — Performa

Tujuan: cold start 30 detik → di bawah 2 detik; tidak ada endpoint yang
menghitung ulang pekerjaan yang sudah ada.

Hasil terukur: cold start 30 detik → ~9 detik (rentang 9-24 detik pada mesin
ini, lihat catatan di bawah). Target 2 detik **tidak tercapai dan tidak bisa
dicapai**: impor pandas/pyarrow saja ~4 detik, dan `pyarrow` membayar ~1,5 detik
sekali saat alokasi pertama, sebelum satu byte data pun dibaca. Yang dihapus
adalah bagian yang memang bisa dihapus: pekerjaan berulang.

- [x] **1.1 GZip** — XS
  - Berkas: `horus_graph/api/app.py`
  - Kerjakan: `app.add_middleware(GZipMiddleware, minimum_size=1024)`.
  - Terima: `curl -H "Accept-Encoding: gzip" -s -o /dev/null -w "%{size_download}"` untuk `/api/bootstrap` < 30.000 byte.
  - Hasil: 141.770 → 20.996 byte (85% turun). `index.html` 66.799 byte ter-gzip.

- ~~**1.2 Artefak pra-hitung** — L~~ **dibatalkan setelah diukur**
  - Berkas: `horus_graph/cli.py:57-118`, `horus_graph/api/state.py`, modul baru `horus_graph/io/artifacts.py`
  - Rencana: `horus-graph build --out` menulis `artifacts/{nodes,links,epochs/*}.parquet` + `metrics.json` + `anomaly.parquet` + `cooc.npz`; API memuatnya bila kunci hash cocok.
  - Alasan batal:
    - Premisnya salah. Startup didominasi impor (pandas/pyarrow ~4 detik) dan
      inisialisasi `pyarrow` (~1,5 detik pada alokasi pertama, ukuran berkas
      tidak berpengaruh). Perhitungan yang bisa dipindahkan ke artefak tinggal
      2,4 detik setelah 1.4 dan perbaikan `subset` di bawah.
    - Yang ditukar bukan hanya 400 baris serialisasi, tapi juga satu kelas bug:
      artefak basi menyajikan angka lama tanpa suara. Itu persis kegagalan yang
      Fase 0 habiskan waktu untuk menghapus, dan tidak ada tombol "muat ulang"
      yang bisa menyelamatkan analis yang tidak tahu artefaknya basi.
    - Kunci hash memang mencegahnya — kalau benar. Satu berkas yang lupa ikut
      di-hash, dan cache menyajikan campuran lama-baru tanpa gejala.
  - Yang dikerjakan sebagai gantinya (efek sama, tanpa permukaan baru):
    - `DataBundle.subset` memakai `isin` pada kolom `str` Arrow yang memanggil
      Python per elemen: `build_temporal` 3,2 s → 1,4 s.
    - `horus_graph.enhance` mengimpor malas; `scipy.stats` (5 detik impor
      pertama) keluar dari jalur impor API.
  - Catatan pengukuran: `serve` pada mesin ini berayun 9-24 detik untuk kode
    yang sama — impor `.pyd` dan pembacaan berkas di sini lambat dan tidak
    stabil. Yang bisa dipercaya adalah pengukuran dalam satu proses:
    tahap bangun 5,5 s → 4,4 s. Angka `serve` jangan dipakai membandingkan
    commit.

- [x] **1.3 `/api/enhance` keluar dari jalur request** — M
  - Berkas: `horus_graph/api/routes.py:263-286`
  - Kerjakan: pindahkan ke artefak build (ikut 1.2) atau jadikan `POST` + cache per `(bundle, resamples, bootstrap_resamples, seed)`. Turunkan default `resamples` 100 → 20.
  - Terima: GET `/api/enhance` tidak ada lagi, atau balas < 100 ms dari cache. Tidak ada request yang menahan threadpool > 1 detik.
  - Hasil: **endpoint dihapus**, bukan di-cache. Alasannya terukur:
    - Tidak ada pemakai. `grep -rn "api/enhance"` hanya menemukan tesnya sendiri;
      UI mengambil semuanya lewat `/api/bootstrap`.
    - Biayanya bukan cache miss sekali, tapi biaya per setelan. null model
      4,8 s pada `resamples=20` dan 16,8 s pada `resamples=100`; bootstrap 3,2 s.
      Cache per `(resamples, bootstrap_resamples, seed)` berarti setiap nilai
      baru yang dicoba pengguna membayar penuh lagi.
    - Sampler sudah di lantai: dari ~240 ms per resample, 136 ms adalah
      `nx.double_edge_swap` (4.750 swap). Mempercepatnya berarti menulis ulang
      sampler, bukan menggeser endpoint.
  - Kemampuan tidak hilang: `horus-graph enhance --json` mengeluarkan blok yang
    sama (null model, bootstrap, topologi, perputaran, burst), dan
    `reporting_block(..., null=, bootstrap=)` sudah siap menempelkannya ke
    provenance bila kelak ada artefak. Bila UI nanti butuh, bentuknya job +
    polling, bukan GET sinkron.
  - Pagar baru: `test_tidak_ada_endpoint_yang_menahan_permintaan` mengukur enam
    endpoint baca dan gagal bila ada yang lewat 1 detik.

- [x] **1.4 Baca parquet sekali** — S
  - Berkas: `horus_graph/io/bundle.py`, `horus_graph/contract/validate.py`
  - Kerjakan: validator mengembalikan frame yang sudah dibaca, `load_bundle` memakainya; sha256 opsional (`--verify-hash`).
  - Terima: startup turun ≥ 1,5 detik; `validate` CLI tetap mendeteksi bundle rusak (tes lama hijau).
  - Hasil: `validate_and_read()` mengembalikan `(temuan, frames)`; `load_bundle`
    memakai frame itu dan hanya membaca ulang bila `strict=False`. `_read_optional`
    diganti `_present()` yang membaca dari dict frame.
  - Koreksi target: penghematan terukur **72 ms**, bukan 1,5 detik. Bacaan kedua
    murah karena cache halaman sudah hangat; yang mahal adalah bacaan pertama
    (2,07 s untuk 3,0 MB) dan itu dibayar sekali oleh validator. Angka 1,5 detik
    di AUDIT berasal dari asumsi yang salah — sudah dikoreksi di sana.
  - sha256 **tetap wajib**: 13,5 ms untuk 3,0 MB, yaitu 0,7% startup. Membuatnya
    opsional akan melemahkan kontrak tanpa keuntungan terukur, jadi `--verify-hash`
    tidak ditambahkan.

- [x] **1.5 Kontrafaktual memakai metrik yang ada** — XS
  - Berkas: `horus_graph/analysis/counterfactual.py:37`
  - Kerjakan: `base_betweenness = network.node_metrics["betweenness"].to_dict()`.
  - Terima: respons `/api/analysis/counterfactual` < 30 ms; `baseline_betweenness` sama dengan nilai di `/api/bootstrap` untuk simpul yang sama.
  - Hasil: 22 ms (hangat). `baseline_betweenness` cocok persis dengan
    `/api/bootstrap`: Persita Tangerang 0,0412 / Karim Rossi 0,0957 /
    PSIS Semarang 0,0724.

- [x] **1.6 `/api/provenance` tanpa payload penuh** — XS
  - Berkas: `horus_graph/api/routes.py:79-81`
  - Kerjakan: panggil `reporting_block(state.bundle, state.network, seed=42)` langsung.
  - Terima: < 50 ms; isi identik dengan sebelumnya.
  - Hasil: 378 ms → 7–10 ms. `PROVENANCE_SEED = 42` dipindah ke `serializers.py`
    supaya bootstrap dan provenance memakai konstanta yang sama.

- [x] **1.7 Bundle diresolusi sekali** — S
  - Berkas: `horus_graph/api/state.py:45-66`, `horus_graph/api/app.py:32`
  - Kerjakan: resolve saat `create_app`, simpan path final di `app.state.bundle_path`; `get_state` tidak lagi memindai `data/bundles/`.
  - Terima: menambah folder baru di `data/bundles/` saat server jalan tidak mengubah dataset yang disajikan (docstring `app.py` jadi benar).
  - Hasil: `run()` meresolusi satu kali lalu menyerahkan path final ke
    `get_state()` dan `create_app()`; docstring `get_state` menyatakan kontrak itu.

- [x] **1.8 Copilot tidak memblokir loop** — S
  - Berkas: `horus_graph/copilot/service.py:150`, `horus_graph/copilot/llm.py:103`
  - Kerjakan: `await run_in_threadpool(tools.execute, ...)` dan `run_in_threadpool(fallback.answer, ...)`; `AsyncOpenAI(..., timeout=30.0, max_retries=1)`.
  - Terima: kirim pertanyaan yang memicu `generate_executive_briefing`, lalu `PING` — `PONG` tetap balik < 500 ms.
  - Hasil: tiga pemanggilan `fallback.answer` dan `tools.execute` lewat
    `run_in_threadpool`; `REQUEST_TIMEOUT_SECONDS = 30.0`, `MAX_RETRIES = 1`.

**Selesai fase 1 bila:** kedelapan butir hijau dan tidak ada endpoint yang
menghitung ulang pekerjaan yang sudah ada.

Status: **selesai** — 7 butir dikerjakan, 1 dibatalkan dengan alasan terukur di
atas. 235 tes lulus. Tiga temuan yang mengubah rencana:
`Number(null)` pada Fase 0, pembacaan ganda parquet yang ternyata hanya 72 ms
(1.4), dan artefak pra-hitung yang ternyata tidak menyentuh biaya terbesar (1.2).

---

## Fase 2 — UX + aksesibilitas

Tujuan: graf terbaca di layar pertama, teks bisa dibaca, dan analis keyboard-only
bisa bekerja.

Status: **selesai** — 10 butir dikerjakan; 254 tes lulus.

- [x] **2.1 Graf mengisi kanvas** — S
  - Berkas: `index.html` (`getCloseFitTransform()`, `canvasInsets()`, `cameraAt()`)
  - Kerjakan: panggil fit-transform sekali setelah layout boot selesai, bukan hanya saat mode berpindah. Simpan zoom/pan saat berpindah mode.
  - Terima: pada 1600×950, graf menempati > 60% tinggi kanvas tanpa interaksi.
  - Hasil: 77% tinggi kanvas pada 1600×950. Dua kesalahan awal ikut diperbaiki: skala
    dihitung dari piksel padahal `viewBox` memakai satuan pengguna, dan fit tidak
    memperhitungkan sidebar/KPI/timeline/dock yang menutup kanvas. Sekarang kamera
    mengukur persegi yang tertutup (`CANVAS_OCCLUDERS`) lalu memusatkan graf di
    sisa ruang; `zoom.scaleExtent` dinaikkan ke `[0.15, 8]` agar fit tidak mentok.

- [x] **2.2 Hapus KPI ganda** — S
  - Berkas: `index.html` kartu atas vs sidebar (`SIMPUL/SISI/DENSITY`)
  - Kerjakan: satu sumber. Pertahankan kartu atas; hapus baris statistik di sidebar.
  - Terima: angka 77/475/0,162 muncul sekali di layar.
  - Hasil: `.sb-stats-bar` dihapus bersama CSS dan penulisnya
    (`updateActiveGraphStatsUnified`). Penulis tunggal sekarang `updateMacroStats()`;
    `updateEdgeCountBadge()` hanya meneruskan angka yang terlihat. Nilai yang tidak
    terukur ditulis `—`, bukan `0`.

- [x] **2.3 Tipografi & kontras** — S
  - Berkas: `index.html:30,85`; `copilot.css:361,509`
  - Kerjakan: `--text-dim` → `#8A99AE` (≈5,4:1); border input → `#475569`; ukuran teks panel minimum 11px, label sekunder 11px.
  - Terima: tidak ada `font-size` < 11px di CSS panel; rasio kontras teks ≥ 4,5:1 (periksa 3 pasangan yang tercatat di AUDIT).
  - Hasil: 11 ukuran font di `copilot.css` dinaikkan ke 11px; `#64748B` (3,4:1) →
    `#8A99AE`; border input `rgba(255,255,255,0.18)` (1,77:1) → `#5A6B82` (3,55:1).
    Dijaga `test_tidak_ada_teks_di_bawah_sebelas_piksel` dan
    `test_teks_sekunder_lolos_kontras`.

- [x] **2.4 Satu bahasa** — S
  - Kerjakan: UI Indonesia; istilah SNA tetap Inggris dan bisa dijelaskan lewat `get_glossary`. Ganti "Mode 01: Actor Network", "View Info", "Search Node", "Top 5", "All-Time".
  - Terima: `grep` label UI tidak lagi mencampur dua bahasa selain istilah teknis.
  - Hasil: label Indonesia di `index.html`, `copilot_ui.js`, `copilot_bridge.js`
    ("Terhubung"/"Terputus", "Lihat Info", "Cari entitas…", "5 Teratas", pil epos
    "Semua", "LEGENDA"). Istilah SNA dibiarkan Inggris. Dijaga
    `test_label_ui_satu_bahasa`, yang memeriksa teks tampilan saja — komentar dan
    baris `console.*` tidak dihitung label.

- [x] **2.5 Toolbar jadi tiga grup** — M
  - Kerjakan: kelompokkan 10 kontrol menjadi Tampilan / Filter / Data. Label tidak boleh terlipat lebih dari satu baris.
  - Terima: tinggi toolbar tetap saat viewport 1280px.
  - Hasil: tiga `.header-group` dengan pemisah `border-left`. Tinggi header 56px
    pada 1280/1440/1600, `overflow = 0` (tepi kanan kontrol 1260 dari batas 1260).
    Yang berkorban adalah judul, bukan kontrol: blok judul menyusut dengan elipsis
    (teks utuh di `title`), sedangkan `.header-controls` `flex: 0 0 auto`. Di bawah
    1360px subjudul dan teks "Filter" disembunyikan, di bawah 1180px pil mode
    menjadi nomor saja, di bawah 980px strip kontrol bisa digeser — tidak ada
    kontrol yang hilang dari DOM.

- [x] **2.6 Drawer sebagai dialog** — S
  - Berkas: `index.html`, `copilot_ui.js`
  - Kerjakan: `role="dialog" aria-modal="true" aria-labelledby`, focus trap, `Esc` menutup, fokus kembali ke `#btn-toggle-copilot`.
  - Terima: Tab tidak keluar drawer; `Esc` menutup; fokus kembali ke tombol pembuka.
  - Hasil: `handleDrawerKeydown` menahan Tab di ujung daftar dan menutup pada
    `Escape`; `closeCopilotDrawer()` mengembalikan fokus ke tombol pembuka.
    Dijaga `test_drawer_menahan_fokus_dan_bisa_ditutup_escape`.

- [x] **2.7 Graf bisa dijangkau keyboard** — M
  - Berkas: `index.html` (simpul), `.sb-entity-row`
  - Kerjakan: `tabindex="0" role="button" aria-label="{label}, {type}, derajat {degree}"` + Enter/Space memanggil handler yang sama dengan klik; `.sb-entity-row` → `<button type="button">`.
  - Terima: Tab dari toolbar mencapai simpul pertama dan setiap baris daftar; Enter memilih simpul dan mengisi panel kanan.
  - Hasil: roving tabindex — satu simpul di urutan Tab, panah memindahkan fokus,
    Enter/Space memilih lewat jalur yang sama dengan klik. `.sb-entity-row` menjadi
    `<button type="button">` dengan `width:100%`. Cincin fokus 3,5px supaya
    terlihat di atas lingkaran gelap.

- [x] **2.8 Chat diumumkan** — XS
  - Berkas: `index.html`
  - Kerjakan: `role="log" aria-live="polite" aria-relevant="additions"` pada body chat; `aria-live="polite"` pada status koneksi.
  - Terima: dengan screen reader, jawaban agen terbaca otomatis.
  - Hasil: badan percakapan `role="log"`, status koneksi `role="status"`.

- [x] **2.9 Bahasa dokumen & gerak** — XS
  - Berkas: `index.html`
  - Kerjakan: `lang="id"`; blok `@media (prefers-reduced-motion: reduce)` mematikan animasi/transisi; `aria-label` untuk tombol glyph (`+`, `−`, `✕`).
  - Terima: `lang="id"`; dengan reduced-motion tidak ada animasi berulang; tidak ada tombol tanpa nama aksesibel.
  - Hasil: `<html lang="id">`, blok reduced-motion, dan 8 tombol glyph diberi
    `aria-label`. Dijaga `test_semua_tombol_punya_nama_aksesibel` dan
    `test_permintaan_mengurangi_gerak_dihormati`.

- [x] **2.10 Satu kontrol waktu** — S
  - Kerjakan: satukan pill epos + titik tahun + slider menjadi satu kontrol. Hapus minimap atau ganti indikator zoom.
  - Terima: hanya satu kontrol waktu terlihat; memilih epos memperbarui semua panel.
  - Hasil: bilah waktu tinggal satu `input[type=range]` plus pil epos; penanda
    peristiwa dipindah ke luar bilah (`bottom:96px`, label "Peristiwa") agar
    tahunnya tidak terbaca sebagai deret kontrol kedua. Minimap dipertahankan
    sebagai indikator posisi dan diberi judul "PETA MINI". Dijaga
    `test_satu_kontrol_waktu_di_bilah`.

---

## Fase 3 — Lapisan enterprise

Tujuan: boleh dipakai lebih dari satu orang dan lebih dari satu mesin.

- [x] **3.1 Autentikasi minimum** — M
  - Berkas: `horus_graph/api/app.py`, `horus_graph/copilot/ws.py`, `horus_graph/cli.py`
  - Kerjakan: `HORUS_API_TOKEN` + dependency `Depends` di router dan handshake WS; tolak bind non-loopback bila token kosong; cek `Origin` pada WS.
  - Terima: tanpa token, request ke `0.0.0.0` ditolak 401; WS dari origin asing ditolak.
  - Hasil: `horus_graph/api/auth.py` — `require_token` sebagai dependency router
    (`/api/*`) dan per-route di `ws.py`; `secrets.compare_digest`, bukan `==`.
    Bind non-loopback tanpa token **ditolak saat start** (`ensure_bind_is_safe`),
    bukan dijawab 401 setelah terbuka — lebih cepat gagal, tidak ada jendela
    terbuka. Handshake WS memeriksa `Origin` terhadap header `Host` dan token
    sebelum `accept()`, lalu menutup dengan 1008. Frontend membaca `?token=…`,
    menyimpannya di `sessionStorage`, menghapusnya dari address bar, dan
    menyuntikkan header lewat pembungkus `fetch`. Diverifikasi di port 8141:
    tanpa token 401, dengan header/query 200, UI terisi penuh.

- [ ] **3.2 Export** — M
  - Kerjakan: `horus-graph export --format graphml|csv|gexf` dan endpoint `/api/export/{format}`. Sertakan atribut metrik per simpul.
  - Terima: GraphML hasil export bisa dibuka di Gephi dengan 77 simpul dan atribut betweenness/constraint.

- [ ] **3.3 Snapshot berversi** — M
  - Kerjakan: `manifest.snapshot_id` = hash isi bundle; riwayat snapshot di `data/bundles/.index.json`; endpoint `/api/datasets` untuk daftar read-only.
  - Terima: dua bundle berbeda tampil sebagai dua snapshot; `/api/health` menyebut `snapshot_id`.

- [x] **3.4 Observability** — S
  - Kerjakan: structured log (JSON) + request id middleware; ganti `print()` di `app.py:65-67`; endpoint `/metrics` (Prometheus text) berisi durasi request dan status.
  - Terima: setiap log punya `request_id`; `/metrics` mengembalikan `http_request_duration_seconds`.
  - Hasil: `horus_graph/api/observability.py`. `RequestContextMiddleware` (ASGI murni,
    tanpa task tambahan) meneruskan atau membuat `x-request-id`, mengembalikannya ke
    klien, dan mencatat satu baris per permintaan. `_JsonFormatter` +
    `_RequestIdFilter` dipasang ke root dan ke logger uvicorn lewat
    `configure_logging()`; `uvicorn.run(..., log_config=None)` supaya dictConfig
    uvicorn tidak menimpa handler JSON. `/metrics` menyajikan
    `horus_http_requests_total` dan `horus_http_request_duration_seconds`
    (11 bucket) tanpa `prometheus_client`. Dua `print()` di `run()` diganti logger.

- [ ] **3.5 Packaging & CI** — M
  - Kerjakan: `Dockerfile` multi-stage, `.github/workflows/ci.yml` (ruff + mypy + pytest), `[tool.ruff]`/`[tool.mypy]` di `pyproject.toml`, `Makefile` dengan `check`.
  - Terima: `docker run` menyajikan UI; CI hijau pada PR kosong.

- [ ] **3.6 Kontrak OpenAPI** — M
  - Kerjakan: `response_model` untuk endpoint yang bentuknya stabil; dokumentasikan endpoint yang sengaja `Dict`.
  - Terima: `/openapi.json` memuat skema untuk minimal 10 endpoint.

- [x] **3.7 Batas & higiene error** — S
  - Berkas: `routes.py:38,69,194,202`
  - Kerjakan: `Query(le=100)` pada semua `limit`; 503 mengembalikan pesan generik + log internal; `/api/dataset/status` hanya nama folder.
  - Terima: `?limit=999999` ditolak 422; respons error tidak memuat path absolut.
  - Hasil: `limit` pada brokers/holes `Query(ge=1, le=100)`, `min_npmi` `ge=-1, le=1`;
    `?limit=999999`, `?limit=0`, `?min_npmi=5` → 422. Kegagalan muat bundle:
    `logger.exception` di server, klien menerima satu kalimat tetap. `root` hanya
    nama folder, dan `BundleNotFound` tidak lagi menyebut path absolut.

- [x] **3.8 XSS ditutup** — S
  - Berkas: `copilot_ui.js:390-392`, `:199,252`
  - Kerjakan: `textContent` untuk judul sesi; sanitizer (DOMPurify atau allowlist) sebelum `innerHTML` hasil `marked`; CSP tanpa `unsafe-inline`.
  - Terima: sesi berjudul `<img src=x onerror=alert(1)>` tampil sebagai teks.
  - Hasil: `sanitizeHtml()` allowlist tag/atribut (tanpa dependensi baru) menyaring
    keluaran `marked` sebelum token KaTeX diganti HTML; `href` di luar
    `http`/`mailto`/`#`/`/` dibuang dan tautan diberi `rel="noopener noreferrer"`.
    `fallbackRegexMarkdown` meng-escape masukan lebih dulu. Daftar sesi dibangun
    dari simpul teks. Dijaga `tests/test_frontend_security.py`.
  - Sisa: CSP belum dipasang. `index.html` memakai atribut `style=` dan skrip
    inline di ratusan tempat, jadi CSP butuh refactor tersendiri; yang ditutup di
    butir ini adalah jalur datanya, bukan kebijakan dokumennya.

---

## Pemangkasan

Dikerjakan kapan saja, tapi jangan mencampur dengan fase lain.

- [ ] **P.1** Hapus `export/legacy.py` + `export/legacy_presentation.py` + extra `[legacy]` (439 baris)
- [ ] **P.2** Hapus `Cooccurrence.as_frame`, `intent.describe`, `topology.core_numbers`, `anomaly.series`
- [ ] **P.3** Hapus `bipartite._media_topic_table` + kolom `media_topics` + `presentation.sankey_columns`
- [ ] **P.4** Hapus parameter `betweenness_samples` beserta cabang aproksimasinya
- [ ] **P.5** Satukan delapan koersi None/NaN jadi satu `horus_graph/_coerce.py`
- [ ] **P.6** Satukan perhitungan `stance` (tiga implementasi, dua pembagi hardcoded)
- [ ] **P.7** Tambah tes untuk `copilot/service.py` (loop tool-calling + fallback saat gateway gagal) dengan klien palsu

---

## Sengaja tidak dikerjakan

| Item | Alasan |
| --- | --- |
| Multi-tenancy penuh | Bertentangan dengan "fork = ganti bundle". Registry read-only (3.3) cukup |
| RBAC per entitas | Belum ada pengguna yang butuh; menambah permukaan tanpa manfaat |
| Streaming/incremental ingest | Pipeline tetap manual di Kaggle; bundle utuh adalah kontrak |
| Real-time collaboration | Belum ada satu pun pengguna bersama |
| Migrasi DB relasional | Parquet + artefak cukup sampai 10× data |

## Urutan eksekusi

```
Fase 0 (integritas)  →  Fase 1 (performa)  →  Fase 2 (UX)  →  Fase 3 (enterprise)
                                    ↘ P.* (pemangkasan, kapan saja)
```

Fase 0 wajib selesai sebelum fase lain dimulai. Fase 1.2 (artefak) boleh
ditunda; 1.1, 1.3–1.8 tidak bergantung padanya.

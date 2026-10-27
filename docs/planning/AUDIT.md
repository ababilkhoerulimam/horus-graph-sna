# Audit 2026-10-27

Audit dilakukan pada commit `2d78525` (M11 selesai). Metode: lima peninjau
terpisah (arsitektur, kualitas kode, keamanan, performa, aksesibilitas) plus
pengukuran langsung pada bundle `horus-agent-2026-10-27` (27.407 artikel,
191.087 mention, 77 simpul, 475 sisi).

Angka di bawah **diukur**, bukan diperkirakan, kecuali yang ditandai "estimasi".

## Ringkasan

| Dimensi | Kondisi | Nilai |
| --- | --- | --- |
| Ukuran | Python 9.179 baris, frontend 8.544 baris | — |
| Tes | 221 lulus | — |
| Permukaan | 24 route HTTP + 1 WebSocket | — |
| Cold start | 30 detik | CPU build hanya 7,3 detik |
| Payload boot | 151,2 KB JSON | 20,7 KB bila gzip |
| Memori | RSS 274 MB setelah boot | 550 MB untuk dua bundle |
| Skala nyaman | ±2.000 simpul / 5.000 sisi | DOM SVG patah lebih dulu |

Kesimpulan: ini workstation analis yang baik, bukan platform enterprise. Yang
kurang bukan fitur, tapi lapisan kepercayaan (otentikasi, artefak berversi,
kejujuran angka di UI) dan satu dekade kebiasaan operasional (CI, container,
observability).

## 1. Integritas — tiga bug yang membatalkan premis produk

Premis repo: "lapisan yang belum ada dilaporkan `awaiting_input`, bukan angka
netral". Engine mematuhinya. UI tidak.

### 1.1 Sentimen karangan

`horus_graph/web/static/index.html:4376-4378`

```js
const sPos = m.sentiment_pos !== undefined ? m.sentiment_pos : 14;
const sNeu = m.sentiment_neu !== undefined ? m.sentiment_neu : 83;
const sNeg = m.sentiment_neg !== undefined ? m.sentiment_neg : 3;
```

Bundle ini punya `network.sentiment = None` (lapisan `awaiting_input`), jadi
**setiap** entitas menampilkan Pos 14% / Neu 83% / Neg 3%, dengan stance
`+0.11` yang dihitung dari angka karangan itu (`:4382`). Tampilannya identik
dengan hasil ukur.

Markup dasarnya juga sudah membawa angka palsu: `index.html:2722` (`+0.28
Stance`), `:2725` (55%/25%/20%), `:2737` (`Total 20%`).

### 1.2 Panel bukti tepi tidak pernah hidup

- UI memanggil `/api/edge/evidence` (`index.html:4219`); route-nya
  `/api/edges/evidence` (`horus_graph/api/routes.py:221`). 404.
- 404 ditelan `res.ok ? res.json() : null` (`:4220`), jadi tidak ada error di
  konsol maupun di panel.
- Setelah path diperbaiki pun panel tetap kosong: UI membaca
  `data.evidence_snippets` (`:4230`), `data.salton_cosine` dan `data.jaccard`
  (`:4224-4226`), serta `sn.snippet` / `sn.source` / `sn.date` (`:4246-4251`).
  Route mengembalikan `evidence`, tanpa `jaccard`/`salton_cosine`, dan tiap
  item berisi `site`/`published_at`/`url`.

### 1.3 Default yang terbaca sebagai data

- `index.html:2755` prioritas default `CRITICAL`, `:2757` peran default
  `high_brokerage_entity`, `:2722` stance default `+0.28`.
- Sebelum ada simpul dipilih, panel kanan menampilkan ketiganya seolah hasil
  analisis.

### 1.4 Nama model vendor di kode

`index.html:2437` menulis `NusaBert NER SOTA`. Ini bukan metadata bundle dan
akan salah begitu repo di-fork untuk dataset lain.

## 2. Performa

### 2.1 Startup

| Tahap | Waktu | Catatan |
| --- | --- | --- |
| `validate_bundle` | 2,07 s | bacaan pertama 5 parquet (3,0 MB) menanggung I/O dingin; sha256 hanya 13,5 ms |
| baca ulang di `load_bundle` | 0,07 s | frame dibaca **dua kali**; bacaan kedua murah karena cache halaman sudah hangat |
| `build_network` | 0,68 s | ~50% di `summary()`: `diameter` + `average_shortest_path_length` = 2×77 BFS |
| `build_temporal` | 4,12 s | 56% konversi Arrow→object di `DataBundle.subset()` |
| `build_bipartite` | 0,75 s | merge 54.615 × 191.087 |
| `detect_anomalies` | 0,58 s | murah |

Sisa dari 30 detik adalah import pyarrow/scipy + baca parquet + sha256 (I/O).

Catatan koreksi: pembacaan ganda sempat dicatat sebagai penyebab utama lambatnya
startup (93%). Setelah diukur per tahap, bacaan kedua hanya 0,07 s — yang mahal
adalah bacaan pertama saat cache masih dingin, dan itu terjadi sekali saja.

### 2.2 Jalur request

| Endpoint | Waktu | Masalah |
| --- | --- | --- |
| `/api/enhance` | **22,7 s** | null model 18,2 s + bootstrap 3,7 s + bursts 0,73 s, sinkron, tanpa cache. `resamples=1000` ≈ 346 s |
| `/api/provenance` | 0,77 s | membangun seluruh payload bootstrap lalu mengambil satu kunci |
| `/api/bootstrap` | 0,58 s | serialisasi ulang tiap request, tanpa gzip |
| `/api/analysis/counterfactual` | 0,11 s | menghitung ulang betweenness yang sudah ada di `node_metrics` |
| `/api/edges/evidence` | 0,085 s | full scan `mentions` dua kali per panggilan |

### 2.3 Payload & memori

- `/api/bootstrap` = 151,2 KB (20,7 KB gzip). Komposisi: `graph` 82%.
- 693 B/simpul, 142 B/sisi. Estimasi `0,69·N + 0,14·E` KB.
- 5.000 simpul → ±7,6 MB tanpa gzip.
- `epochs[].node_ids` menduplikasi `graph.nodes`.
- RSS: 15 MB (import) → 183 MB (bundle) → 274 MB (state lengkap).
- `lru_cache(maxsize=2)` menahan dua salinan → ±550 MB.

### 2.4 Frontend

- 77 simpul + 475 sisi ≈ 1.700 elemen SVG. Masih aman.
- `alphaDecay(0.022)` ≈ 311 tick, tiap tick menulis ulang semua transform
  simpul dan 2 path per sisi ≈ **295.000 string path** saat boot.
- `applyCombinedFilters` memaku `fx/fy` untuk semua simpul, jadi simulasi
  gaya itu dekoratif.
- Pada 5.000 simpul: ±90.000 elemen SVG, 18,6 juta pembaruan path.

### 2.5 Blokir event loop

`horus_graph/copilot/service.py:150` memanggil `tools.execute()` sinkron di
dalam coroutine. `generate_executive_briefing` atau `simulate_what_if_scenario`
membekukan seluruh HTTP dan WebSocket selama berjalan. `llm.py:103` membuat
`AsyncOpenAI` tanpa `timeout`/`max_retries`.

## 3. Keamanan

Tidak ada `subprocess`, `eval`, `pickle`, atau SQL di seluruh paket. Kelas
injeksi klasik tidak ada. Yang nyata:

| Severity | Temuan |
| --- | --- |
| KRITIS | Tidak ada autentikasi di 24 route + `/ws/copilot`. `--host 0.0.0.0` tanpa peringatan, tanpa `TrustedHostMiddleware`, tanpa cek `Origin` |
| KRITIS | `/api/enhance` = DoS CPU tanpa kuota; 40 request paralel mematikan seluruh threadpool |
| KRITIS | Amplifikasi biaya LLM: satu pesan = sampai 3 panggilan model dengan 20 skema tool; tanpa rate limit, tanpa batas panjang pesan |
| TINGGI | Cross-site WebSocket hijacking (WS tidak tunduk CORS, `Origin` tidak diperiksa) |
| TINGGI | IDOR sesi chat: `GET /api/chat/sessions` mengembalikan semua sesi semua orang; `DELETE` bisa menghapus milik siapa pun |
| TINGGI | Stored XSS lewat judul sesi (`copilot_ui.js:390-392` merender `s.title` via `innerHTML`) |
| TINGGI | XSS lewat output model: `marked.parse()` tanpa sanitizer, dan judul artikel dari dataset masuk ke konteks model |
| TINGGI | Path absolut bocor di `/api/dataset/status` (`routes.py:69`) dan di pesan 503 (`routes.py:38`) |
| SEDANG | `limit` tanpa batas di `/api/analysis/brokers` dan `/holes` |
| SEDANG | D3 punya fallback CDN tanpa SRI (`index.html:11`) |

Catatan jujur: untuk satu analis di localhost, sebagian besar tidak relevan.
Yang tetap layak diperbaiki bahkan di lokal: biaya `/api/enhance`, memori
sesi, dan XSS dari bundle hasil fork yang tidak dikenal.

## 4. Aksesibilitas (WCAG 2.2 AA)

Gagal di pintu masuk. Tiga blocker:

1. `g.node-item` dibuat dengan `.on("click")` tanpa `tabindex`/`role`/`aria-label`
   (`index.html:3846-3856`). Graf, inti produk, tidak pernah menerima fokus.
2. Satu-satunya alternatif non-visual, `.sb-entity-row` (`:5708`), berupa `div`
   tanpa `tabindex` — jadi alternatifnya pun mouse-only.
3. `#copilot-chat-body` (`:2677`) tanpa `aria-live`; respons agen tidak pernah
   diumumkan.

Kontras yang gagal: `#64748B` pada `#050505` = 4,28:1 (`:30`, `.rail-btn` `:85`);
`#64748B` pada `#131B2B` = 3,62:1 (`copilot.css:509`); border input
`rgba(255,255,255,.18)` = 1,77:1 (`copilot.css:361`).

Lain-lain: `lang="en"` padahal UI Indonesia (`:2`); drawer tanpa `role="dialog"`,
tanpa `Esc`, tanpa focus trap, tanpa pengembalian fokus; `outline:none` di lima
tempat; tanpa `prefers-reduced-motion`; target sentuh chip ±17px.

## 5. Kode mati dan duplikasi

| Item | Bukti |
| --- | --- |
| `export/legacy.py` + `export/legacy_presentation.py` (439 baris) | Migrasi sekali jalan |
| `Cooccurrence.as_frame` | Nol pemanggil, nol tes |
| `intent.describe` | Nol pemanggil |
| `enhance/topology.core_numbers` | Dihitung penuh, tidak pernah masuk `as_dict()` |
| `bipartite._media_topic_table` | Dibangun tiap boot, hanya dibaca tes |
| `anomaly.series` | Hanya dibaca tes; payload menyusun ulang dari `monthly_counts` |
| `build.betweenness_samples` | Tidak pernah diisi; cabang aproksimasi mati |
| `presentation.sankey_columns` | Kosong, nol referensi UI |
| Delapan salinan koersi None/NaN | `serializers.py:290`, `queries.py:154`, `dossier.py:181`, `tools.py:652`, `build.py:204`, `centrality.py:94`, `nullmodel.py:148`, `topology.py:98` |

Tiga dari koersi itu (`dossier._float`, `tools._num`, `queries._float`)
memanggil `float(value)` tanpa guard dan melempar `TypeError` pada `pd.NA`.

## 6. Cakupan tes

221 tes, tapi dua jalur terpenting tanpa tes: `copilot/service.py` (loop
tool-calling, fallback saat gateway gagal) dan `copilot/llm.py`. Penyebabnya
`openai` tidak terpasang di dev group, sehingga jalur itu tidak pernah
dieksekusi. `cli.py` juga tanpa tes langsung.

## 7. Keputusan yang diambil dari audit ini

1. **Integritas sebelum fitur.** Fase 0 dikerjakan lebih dulu, tanpa
   pengecualian.
2. **`enhance/` tidak dipotong, tapi keluar dari jalur request.** Nilai
   ilmiahnya tinggi; yang salah adalah menghitungnya saat pengguna menunggu.
3. **`copilot/` tidak dipotong.** Ia pembeda produk dan sudah jalan. Yang
   ditunda adalah mengeksposnya ke jaringan tanpa autentikasi.
4. **Multi-tenancy tidak dibangun.** Bertentangan dengan keputusan "fork =
   ganti bundle". Yang dibangun adalah registry dataset read-only.
5. **Satu bahasa untuk UI.** Istilah SNA tetap Inggris, sisanya Indonesia.

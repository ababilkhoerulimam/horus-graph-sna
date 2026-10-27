# horus-graph

Engine SNA modular dan domain-agnostic. Engine ini tidak tahu cara mengambil
data: ia menerima **bundle** (parquet + manifest) yang dihasilkan pipeline di
luar repo ini, lalu menghitung jaringan dan metriknya.

```
pipeline (Kaggle)  →  bundle/  →  horus_graph  →  aplikasi
```

## Kontrak bundle v1.1

```
bundle/
  manifest.json                  # versi kontrak, snapshot, counts, sha256, status layer, presentation
  domain.json                    # ego, epos, tipe entitas
  entities.parquet               # entity_id, entity_type, label, aliases, first_seen
                                 # + opsional: description, cluster, color, tier,
                                 #   ring_level, sector, is_anchor
  articles.parquet               # article_id, source_id, published_at (UTC), url_hash, ...
  mentions.parquet               # article_id, entity_id, count, confidence, matcher_version
  topics.parquet                 # topic_id, label, keywords
  article_topics.parquet         # article_id, topic_id, score
  layers/transmission.parquet    # opsional: alpha, alpha_ci_*, lead_time_min, method
  layers/sentiment.parquet       # opsional: pos, neu, neg, method
```

Tidak ada tabel edge: edge ko-okurensi dihitung engine dari `mentions`, sehingga
hanya ada satu sumber kebenaran.

### Metadata tampilan (`manifest.presentation`)

Seluruh judul, warna, label, dan narasi berasal dari sini — repo ini tidak
memuat nama domain apa pun. Semua field opsional; yang tidak diisi jatuh ke
default netral (`Simpul`, `Sisi`, `Kepadatan`, ...).

```json
{
  "title": "...", "subtitle": "...",
  "ego": {"id": "...", "label": "...", "role": "..."},
  "entity_types": [{"id": "Person", "label": "...", "color": "#..."}],
  "clusters": [{"id": "HUB_A", "label": "...", "color": "#..."}],
  "palette": {"community": ["#..."], "node": "#...", "ego": "#..."},
  "orbit_tiers": ["PUSAT", "LUAR"],
  "epoch_narratives": {"2021": "..."},
  "labels": {"node": "Aktor"},
  "wording": {"no_bundle": "..."},
  "action_rules": {"broker": {"title": "...", "body": "{label} ..."}},
  "sankey_columns": ["Sumber", "Isu", "Aktor"],
  "radius_scale": {"min": 11, "max": 47}
}
```

`ego` boleh kosong. Dataset tanpa satu simpul pusat (kebakaran lahan, misalnya)
cukup mengosongkan `domain.ego_id`; engine mengembalikan `ego: null` dan
visualizer memakai cabang tanpa pusat — tidak ada cincin nol, tidak ada
"jarak dari pusat", dan rantai sebab-akibat ditampilkan tanpa simpul tengah.

Fork = taruh bundle baru, jalankan. Tidak ada kode yang perlu disunting.

Metadata tampilan boleh ditulis sebagai berkas JSON dan dipakai ulang saat
mengekspor: `presentation/horus-agent.json` adalah contoh lengkap (judul,
deskripsi entitas, aturan tindakan, istilah). Ekspor dengan berkas itu:

```bash
horus-graph export-legacy <repo-lama> data/bundles/<nama> \
  --presentation presentation/horus-agent.json
```

## Pakai

```bash
horus-graph validate path/to/bundle    # 0 error berarti patuh
horus-graph info path/to/bundle        # ringkasan counts + status layer
horus-graph build path/to/bundle       # bangun jaringan + metrik
horus-graph build path/to/bundle --all # + irisan epos, bipartit, anomali
horus-graph build path/to/bundle --json --top 10

horus-graph dossier path/to/bundle "Nama Entitas"
horus-graph path path/to/bundle "Asal" "Tujuan"
horus-graph counterfactual path/to/bundle "Nama Entitas"
horus-graph briefing path/to/bundle
horus-graph enhance path/to/bundle    # null model, bootstrap, topologi, perputaran, burst
horus-graph enhance path/to/bundle --json --resamples 200 --bootstrap-resamples 200

horus-graph serve                     # API + visualizer di http://127.0.0.1:8000
horus-graph serve --bundle path/to/bundle --port 8080
```

`serve` memilih bundle lewat urutan: `--bundle` → `HORUS_BUNDLE` → bundle
terbaru di `data/bundles/`. Tanpa bundle, API tetap hidup dan mengembalikan 503
dengan pesan yang bisa ditampilkan UI — bukan mati saat start.

```python
from horus_graph import load_bundle
from horus_graph.core import build_bipartite, build_network, build_temporal, detect_anomalies
from horus_graph.analysis import (
    entity_dossier, executive_briefing, simulate_removal, trace_path,
)

bundle = load_bundle("path/to/bundle")
print(bundle.counts(), bundle.layer_status("transmission"))

network = build_network(bundle)          # BackboneConfig(min_support=3, min_npmi=0.2)
print(network.summary)                   # densitas, modularitas, komponen
print(network.node_metrics.head())       # degree, betweenness, constraint, komunitas
print(network.provenance())              # metode + populasi di balik setiap angka

temporal = build_temporal(bundle)        # satu subgraf per epos + all_time
bipartite = build_bipartite(bundle)      # topik x aktor, media dikecualikan
anomaly = detect_anomalies(bundle)       # robust z per bulan

print(entity_dossier(network, "Nama Entitas", temporal=temporal))
print(trace_path(network, "Asal", "Tujuan"))
print(simulate_removal(network, "Nama Entitas"))
print(executive_briefing(network, temporal, anomaly, bipartite))

from horus_graph.enhance import (
    bootstrap_network, degree_preserving_null, reporting_block, topology_profile,
)

null = degree_preserving_null(network, resamples=200)
boot = bootstrap_network(network, resamples=200)
print(null.as_dict())                    # z + p empiris vs graf acak derajat sama
print(boot.betweenness)                  # mean, sd, ci_low, ci_high, stability
print(reporting_block(bundle, network, null=null, bootstrap=boot,
                      topology=topology_profile(network)))
```

Fungsi analisis mengembalikan dict siap-JSON, bukan model respons. Engine
menjamin angka dan statusnya; penyusunan kalimat ada di lapisan aplikasi karena
itu urusan bahasa dan konteks domain.

## Pipeline komputasi

```
mentions ──► incidensi biner (artikel × entitas, sparse)
         ──► BᵀB = co-occurrence
         ──► NPMI (denominator = seluruh artikel bertanggal)
         ──► ambang support/NPMI + penyelamatan konektivitas
         ──► graf berbobot ──► sentralitas + Louvain

articles.published_at ──► jendela epos ──► subgraf per epos (denominator ikut menyusut)
articles × article_topics ──► n_t ──┐
mentions                    ──► n_a ──┴─► NPMI topik-aktor (media dikecualikan)
articles.published_at       ──► hitung per bulan ──► robust z (median + MAD)
```

`count` pada `mentions` tidak dipakai sebagai bobot: satu artikel yang menyebut
nama sepuluh kali tetap satu kejadian, kalau tidak NPMI naik tanpa asosiasi
yang lebih nyata. Edge hasil penyelamatan ditandai `rescued=True` dan dihitung
terpisah di `backbone.added_for_support`, jadi pembaca bisa membedakan edge
yang lolos ambang dari yang hanya menjaga graf tetap terhubung.

## Peningkatan (M6)

Angka jaringan tunggal tidak punya pembanding maupun ketidakpastian. Modul
`horus_graph.enhance` menutup tiga celah itu tanpa mengubah graf dasar:

| Pertanyaan | Metode | Hasil pada bundle horus-agent |
| --- | --- | --- |
| Apakah struktur ini lebih dari acak? | null model derajat-terjaga (`double_edge_swap`) | modularitas 0,3872 vs 0,1761 (z 27,7); transitivitas 0,7352 vs 0,3127 (z 71,3); p 0,0198 |
| Seberapa yakin angka betweenness? | bootstrap artikel pada matriks incidensi | ARI komunitas 0,9152 [0,7983; 1,0] pada 50 resample |
| Di mana inti jaringan? | k-core + asortativitas | k-core maks 15, 18 simpul inti, 59 pinggiran |
| Berapa banyak yang berubah antar epos? | Jaccard tepi berurutan | 2 transisi, Jaccard rata-rata 0,428 |
| Kapan entitas meledak? | Kleinberg dua keadaan (Viterbi) | 244 rentang, lift tertinggi 10,94 |

Bootstrap mengambil ulang **artikel**, bukan tepi: meresample tepi akan merusak
struktur derajat dan menghasilkan selang yang terlalu sempit. p-value empiris
memakai koreksi +1, jadi laporan tidak pernah mengklaim p = 0 — nilai minimum
yang bisa dilaporkan adalah `1/(resamples+1)`.

`reporting_block()` merangkum semuanya, termasuk batasan yang wajib ikut:
ko-okurensi bukan kausalitas, ambang adalah pilihan analis, lapisan yang belum
ada dilaporkan `awaiting_input` (bukan nol), edge `rescued` dihitung terpisah,
presisi tanggal, dan resolusi p-value.

## API

Satu proses = satu bundle. Semua panel membaca `AppState` yang sama, sehingga
angka tidak mungkin berbeda antar tampilan.

| Endpoint | Isi |
| --- | --- |
| `GET /api/bootstrap` | seluruh data boot: presentasi, graf, epos, topik, indeks entitas, cakupan, anomali, provenance |
| `GET /api/graph/overview` | ringkasan makro |
| `GET /api/graph/compare?baseline=&target=` | delta degree/betweenness/constraint antar epos |
| `GET /api/entities/{id}` | dossier satu entitas |
| `GET /api/analysis/path?origin=&target=` | rute terkuat + alternatif |
| `GET /api/analysis/counterfactual?entity=` | simulasi penghapusan simpul |
| `GET /api/analysis/brokers`, `/holes`, `/briefing` | peringkat dan ringkasan |
| `GET /api/edges/evidence?source=&target=` | artikel yang menyebut kedua entitas |
| `GET /api/topics/actor-network` | bipartit topik-aktor |
| `GET /api/temporal`, `/api/provenance` | epos dan asal angka |
| `GET /api/health`, `/api/dataset/status` | status proses dan kapabilitas (`copilot`, `llm`) |

Tidak ada endpoint passthrough artefak JSON: UI membaca `/api/bootstrap` sekali,
bukan enam berkas terpisah.

Inferensi statistik (null model, bootstrap, topologi, perputaran epos, burst)
tidak punya endpoint HTTP. Pekerjaan itu memakan 22 detik pada setelan bawaan
dan 346 detik pada `resamples=1000`, jadi tempatnya di `horus-graph enhance`
yang mengeluarkan JSON siap tempel, bukan di dalam satu GET yang bisa dipanggil
siapa pun tanpa kuota.

## Copilot (M10)

Drawer tanya-jawab punya dua jalur dan satu set tool:

| Jalur | Syarat | Sumber kalimat |
| --- | --- | --- |
| LLM + tool calling | `HORUS_LLM_BASE_URL`, `HORUS_LLM_MODEL`, ekstra `[llm]` | model |
| Deterministik | selalu aktif | `presentation.wording` |

Keduanya memanggil `horus_graph.copilot.tools` yang membaca `AppState` yang
sama dengan endpoint HTTP, jadi angka di drawer tidak bisa berbeda dari kanvas.
Tanpa gateway, copilot tetap menjawab soal topologi, broker, lubang struktural,
jalur, sentimen, topik, anomali, dan simulasi.

```bash
pip install "horus-graph[api,llm]"
export HORUS_LLM_BASE_URL=http://127.0.0.1:20130/v1
export HORUS_LLM_MODEL=<nama-model-di-gateway>
horus-graph serve
```

| Endpoint | Isi |
| --- | --- |
| `WS /ws/copilot` | percakapan, dossier saat simpul diklik, perintah kanvas |
| `GET /api/copilot/tools` | daftar tool, status LLM, salam pembuka |
| `GET/POST /api/chat/sessions` | riwayat sesi (memori proses) |
| `GET /api/chat/sessions/{id}/messages`, `DELETE` | isi dan hapus sesi |

Persona, contoh pertanyaan, dan deskripsi 20 tool dirakit dari `presentation`:
judul, `ego.label`, `entity_types`, dan contoh entitas diambil dari simpul
berderajat tertinggi. Fork repo + bundle baru cukup mengganti bundle. Kalimat
jawaban deterministik ada di `DEFAULT_WORDING` dan bisa ditimpa per bundle lewat
`manifest.presentation.wording`.

## Prinsip

1. Engine tanpa IO jaringan, tanpa SQLite, tanpa nama domain di dalam kode.
2. Bundle menjelaskan dirinya sendiri: `manifest` + `domain`.
3. Layer opsional membawa statusnya sendiri (`ready` / `awaiting_input`);
   engine mengembalikan `None`, bukan angka netral.
4. Kontrak divalidasi dua arah: data yang hilang ditolak, data yang diklaim
   tanpa isi juga ditolak.
5. Prinsip yang sama berlaku di layar: yang belum diukur tampil kosong
   (`—` atau `awaiting_layer`), tidak pernah angka netral. Dijaga
   `tests/test_frontend_integrity.py`.

## Status

- [x] M0 kontrak: skema, model, validator, loader/writer, CLI
- [x] M1 exporter korpus lama → bundle (27.407 artikel, 191.087 mention, 2,5 MB)
- [x] M2 core build + metrik (golden test vs 77/475/0.1623 — lulus persis)
- [x] M3 temporal, bipartite, anomali (epos 387/436/421/467 edge, 280 edge bipartit, 70 bulan)
- [x] M4 analysis: dossier, rute, kontrafaktual, peringkat broker, briefing
- [x] M5 layer transmission & sentiment (dua arah: kosong → `None`, terisi → dipakai)
- [x] M6 enhance: null model, bootstrap CI, community stability, k-core, turnover
- [x] M7 kontrak presentasi v1.1: kolom opsional entitas + `manifest.presentation`
- [x] M8 API: `/api/bootstrap` dan seluruh endpoint analisis
- [x] M9 visualizer: port HTML, cabut seluruh hardcode domain
- [x] M10 copilot opsional: `[llm]` extra, prompt dibangun dari `presentation`
- [x] M11 horus-agent diarsipkan, menunjuk ke repo ini
- [x] Fase 0 audit: sentimen jujur, panel bukti tepi hidup, default karangan
      dihapus, pagar integritas frontend

Rencana kerja dan audit lengkap ada di [`docs/planning/`](docs/planning/README.md):
[`AUDIT.md`](docs/planning/AUDIT.md) untuk bukti pengukuran,
[`ROADMAP.md`](docs/planning/ROADMAP.md) untuk empat fase perbaikan.

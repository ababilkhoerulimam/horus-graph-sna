# horus-graph

Engine SNA modular dan domain-agnostic. Engine ini tidak tahu cara mengambil
data: ia menerima **bundle** (parquet + manifest) yang dihasilkan pipeline di
luar repo ini, lalu menghitung jaringan dan metriknya.

```
pipeline (Kaggle)  →  bundle/  →  horus_graph  →  aplikasi (horus-agent)
```

## Kontrak bundle v1

```
bundle/
  manifest.json                  # versi kontrak, snapshot, counts, sha256, status layer
  domain.json                    # ego, liga, epos, tipe entitas
  entities.parquet               # entity_id, entity_type, label, aliases, first_seen
  articles.parquet               # article_id, source_id, published_at (UTC), url_hash, ...
  mentions.parquet               # article_id, entity_id, count, confidence, matcher_version
  topics.parquet                 # topic_id, label, keywords
  article_topics.parquet         # article_id, topic_id, score
  layers/transmission.parquet    # opsional: alpha, alpha_ci_*, lead_time_min, method
  layers/sentiment.parquet       # opsional: pos, neu, neg, method
```

Tidak ada tabel edge: edge ko-okurensi dihitung engine dari `mentions`, sehingga
hanya ada satu sumber kebenaran.

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
```

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

## Prinsip

1. Engine tanpa IO jaringan, tanpa SQLite, tanpa nama domain di dalam kode.
2. Bundle menjelaskan dirinya sendiri: `manifest` + `domain`.
3. Layer opsional membawa statusnya sendiri (`ready` / `awaiting_input`);
   engine mengembalikan `None`, bukan angka netral.
4. Kontrak divalidasi dua arah: data yang hilang ditolak, data yang diklaim
   tanpa isi juga ditolak.

## Status

- [x] M0 kontrak: skema, model, validator, loader/writer, CLI
- [x] M1 exporter korpus lama → bundle (27.407 artikel, 191.087 mention, 2,5 MB)
- [x] M2 core build + metrik (golden test vs 77/475/0.1623 — lulus persis)
- [x] M3 temporal, bipartite, anomali (epos 387/436/421/467 edge, 280 edge bipartit, 70 bulan)
- [x] M4 analysis: dossier, rute, kontrafaktual, peringkat broker, briefing
- [ ] M5 layer transmission & sentiment
- [ ] M6 enhance: null model, bootstrap CI, community stability, k-core, turnover

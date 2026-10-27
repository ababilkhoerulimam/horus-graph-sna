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
```

```python
from horus_graph import load_bundle

bundle = load_bundle("path/to/bundle")
print(bundle.counts(), bundle.layer_status("transmission"))
```

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
- [ ] M2 core build + metrik (golden test vs 77/475/0.1623)
- [ ] M3 temporal, bipartite, anomali
- [ ] M4 analysis: dossier, path, what-if, briefing
- [ ] M5 layer transmission & sentiment
- [ ] M6 enhance: null model, bootstrap CI, community stability, k-core, turnover

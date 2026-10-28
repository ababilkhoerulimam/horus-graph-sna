"""
Tool deterministik untuk copilot.

Setiap tool membaca `AppState` yang sama dengan endpoint HTTP, jadi angka yang
disebut copilot identik dengan angka di visualizer. Deskripsi tool dirakit dari
`Presentation` dan katalog entitas: contoh nama entitas diambil dari simpul
berderajat tertinggi, bukan ditulis di kode.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .._coerce import to_number
from ..analysis import (
    entity_dossier,
    executive_briefing,
    sentiment_ranking,
    simulate_removal,
    structural_holes,
    top_brokers,
    trace_path,
)
from ..analysis.resolve import resolve_candidates, resolve_entity, unresolved_share
from ..api import queries
from ..api.state import AppState
from . import specs
from .prompt import centre_label, has_centre
from .specs import CANVAS_ACTIONS

GLOSSARY: Dict[str, str] = {
    "degree": "Jumlah relasi langsung satu simpul. Ukuran paling kasar untuk seberapa sering entitas muncul bersama entitas lain.",
    "betweenness": "Porsi lintasan terpendek antar semua pasangan yang melewati simpul ini. Tinggi berarti simpul menjadi jembatan.",
    "closeness": "Kebalikan jarak rata-rata ke seluruh simpul lain. Tinggi berarti informasi cepat menjangkau seluruh jaringan.",
    "pagerank": "Kepentingan yang merambat lewat relasi berbobot. Simpul penting bila bertetangga dengan simpul penting.",
    "constraint": "Network constraint Burt. Rendah berarti simpul bebas menjembatani kelompok yang terpisah; tinggi berarti terkunci dalam clique yang redundan.",
    "effective_size": "Effective size Burt: jumlah tetangga yang tidak saling terhubung, yaitu ukuran otonomi struktural.",
    "structural_hole": "Lubang struktural adalah celah antara dua kelompok yang jarang terhubung. Simpul yang menutupnya memegang kontrol informasi.",
    "modularity": "Seberapa kuat jaringan terpecah menjadi komunitas. Nilai tinggi berarti batas antar komunitas tegas.",
    "density": "Rasio relasi yang benar-benar ada terhadap seluruh relasi yang mungkin.",
    "npmi": "Normalized pointwise mutual information. Positif berarti dua entitas muncul bersama lebih sering daripada kebetulan.",
    "louvain": "Algoritma deteksi komunitas berbobot. Setiap simpul diberi satu nomor komunitas.",
    "lead_time": "Selisih waktu antara kemunculan berita di sumber dan di penerima, dipakai pada lapisan transmisi.",
    "burt": "Rujukan ke Ronald Burt: constraint dan effective size dipakai untuk mengukur lubang struktural.",
    "broker": "Simpul perantara: betweenness tinggi karena banyak lintasan terpendek melewatinya.",
}

_DISPATCH: Dict[str, Callable[[AppState, Dict[str, Any]], Dict[str, Any]]] = {}


def tool(name: str):
    def register(fn):
        _DISPATCH[name] = fn
        return fn

    return register


def _entity(state: AppState, name: Any) -> str:
    text = str(name or "").strip()
    if not text:
        raise KeyError("Nama entitas kosong.")
    resolved = resolve_entity(state.network, text)
    if resolved is None:
        # Ambigu bukan sama dengan tidak ada: pengguna perlu tahu kandidatnya,
        # bukan disuruh menebak ulang dari katalog lengkap.
        candidates = resolve_candidates(state.network, text)
        if candidates:
            options = ", ".join(candidates)
            raise KeyError(f"'{text}' ambigu: {options}. Sebutkan nama lengkap atau id.")
        raise KeyError(f"Entitas '{text}' tidak ditemukan di katalog.")
    return resolved


def _awaiting(state: AppState, layer: str) -> Dict[str, Any]:
    return {
        "status": "awaiting_input",
        "layer": layer,
        "message": state.presentation.text(
            "awaiting_layer", f"Lapisan {layer} belum tersedia pada bundle ini."
        ),
    }


def _descriptions(state: AppState) -> Dict[str, str]:
    meta = state.bundle.manifest.presentation
    value = getattr(meta, "entity_descriptions", None) if meta is not None else None
    return dict(value) if isinstance(value, dict) else {}


# --- 1. ringkasan ----------------------------------------------------------


@tool("get_network_overview")
def get_network_overview(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    summary = state.network.summary
    communities = summary.get("communities") or {}
    return {
        "status": "ready",
        "dataset": state.bundle.manifest.dataset_id,
        "title": state.presentation.title,
        "centre": centre_label(state),
        "has_centre": has_centre(state),
        "nodes": summary.get("nodes"),
        "edges": summary.get("edges"),
        "density": summary.get("density"),
        "transitivity": summary.get("transitivity"),
        "diameter": summary.get("diameter"),
        "average_path_length": summary.get("average_path_length"),
        "components": summary.get("components"),
        "isolated": summary.get("isolated"),
        "communities": communities.get("count"),
        "modularity": communities.get("modularity"),
        "articles": state.network.corpus_articles,
        "year_span": list(state.temporal.year_span),
        "layers": dict(state.network.layers),
    }


# --- 2. profil -------------------------------------------------------------


@tool("get_entity_dossier")
def get_entity_dossier(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    entity_id = _entity(state, args.get("entity_name"))
    dossier = entity_dossier(state.network, entity_id, temporal=state.temporal)
    description = _descriptions(state).get(dossier["id"])
    if description:
        dossier["description"] = description
    dossier["status"] = "ready"
    return dossier


# --- 3. jalur --------------------------------------------------------------


@tool("trace_causal_path")
def trace_causal_path(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    result = trace_path(state.network, str(args.get("origin", "")), str(args.get("target", "")))
    result["status"] = "ready" if result.get("success") else str(result.get("reason"))
    return result


# --- 4. subgraf ------------------------------------------------------------


@tool("filter_subgraph")
def filter_subgraph(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    start = _as_int(args.get("start_year"), state.temporal.year_span[0])
    end = _as_int(args.get("end_year"), state.temporal.year_span[1])
    topic = str(args.get("topic") or "ALL").strip()

    windows = [
        item
        for item in state.temporal.slices
        if item.window.id != "all_time"
        and item.window.start_year <= end
        and item.window.end_year >= start
    ]
    if not windows:
        return {
            "status": "empty",
            "message": f"Tidak ada epos pada rentang {start}-{end}.",
            "node_ids": [],
        }

    node_ids: set[str] = set()
    for item in windows:
        node_ids.update(str(node) for node in item.graph.nodes)

    if topic and topic.upper() != "ALL":
        # `membership` memetakan topic_id ke daftar entitas, bukan sebaliknya.
        keep = {str(entity_id) for entity_id in state.bipartite.membership.get(topic, ())}
        if not keep:
            return {
                "status": "empty",
                "message": f"Topik '{topic}' tidak dikenal.",
                "node_ids": [],
                "available_topics": specs.topic_ids(state),
            }
        node_ids &= keep

    return {
        "status": "ready",
        "epochs": [item.window.id for item in windows],
        "topic": topic,
        "node_ids": sorted(node_ids),
        "count": len(node_ids),
    }


# --- 5. broker -------------------------------------------------------------


@tool("get_broker_ranking")
def get_broker_ranking(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    ranking = top_brokers(
        state.network,
        entity_type=args.get("entity_type"),
        limit=_as_int(args.get("limit"), 5),
    )
    return {"status": "ready", "entity_type": args.get("entity_type"), "ranking": ranking}


# --- 6-7. transmisi --------------------------------------------------------


@tool("get_hawkes_transmissions")
def get_hawkes_transmissions(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    layer = state.network.transmission
    if layer is None:
        return _awaiting(state, "transmission")

    rows = [
        {
            "source": str(source),
            "target": str(target),
            "alpha": _num(data.get("alpha")),
            "alpha_ci": [_num(data.get("alpha_ci_low")), _num(data.get("alpha_ci_high"))],
            "lead_time_min": _num(data.get("lead_time_min")),
            "method": data.get("method"),
            "n_events": data.get("n_events"),
        }
        for source, target, data in layer.graph.edges(data=True)
    ]
    rows.sort(key=lambda item: -(item["alpha"] or 0.0))
    return {
        "status": "ready",
        "method": layer.method,
        "edge_count": layer.n_edges,
        "transmissions": rows[: int(args.get("limit") or 50)],
    }


@tool("explain_wire_transmission")
def explain_wire_transmission(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    layer = state.network.transmission
    if layer is None:
        return _awaiting(state, "transmission")

    source = _entity(state, args.get("source_media"))
    target = _entity(state, args.get("target_media"))
    if not layer.graph.has_edge(source, target):
        return {
            "status": "not_found",
            "message": f"Tidak ada tepi transmisi dari {source} ke {target}.",
            "has_reverse": layer.graph.has_edge(target, source),
        }

    data = layer.graph.edges[source, target]
    return {
        "status": "ready",
        "source": source,
        "target": target,
        "alpha": _num(data.get("alpha")),
        "alpha_ci": [_num(data.get("alpha_ci_low")), _num(data.get("alpha_ci_high"))],
        "lead_time_min": _num(data.get("lead_time_min")),
        "method": data.get("method"),
        "n_events": data.get("n_events"),
        "window": [data.get("window_start"), data.get("window_end")],
    }


# --- 8. korpus -------------------------------------------------------------


@tool("search_news_narratives")
def search_news_narratives(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query") or "").strip()
    limit = _as_int(args.get("limit"), 10)
    articles = state.bundle.articles
    if articles.empty or not query:
        return {"status": "empty", "message": "Kueri kosong atau korpus tidak ada.", "matches": []}

    subset = articles
    entity_name = args.get("entity_name")
    if entity_name:
        entity_id = _entity(state, entity_name)
        mentions = state.bundle.mentions
        ids = set(
            mentions.loc[mentions["entity_id"].astype(str) == entity_id, "article_id"].astype(str)
        )
        subset = subset[subset["article_id"].astype(str).isin(ids)]

    titles = subset["title"].astype(str)
    matched = subset[titles.str.contains(query, case=False, regex=False, na=False)]
    matched = matched.head(max(0, limit))

    return {
        "status": "ready",
        # Bundle kontrak ini hanya membawa judul, bukan isi artikel. Dinyatakan
        # terbuka supaya jawaban tidak mengklaim kutipan yang tidak ada.
        "text_available": False,
        "match_count": int(len(matched)),
        "matches": [
            {
                "article_id": str(row["article_id"]),
                "title": row.get("title"),
                "site": row.get("source_id"),
                "published_at": row.get("published_at"),
                "url": row.get("url") if "url" in row.index else None,
            }
            for _, row in matched.iterrows()
        ],
    }


# --- 9. sentimen -----------------------------------------------------------


@tool("get_sentiment_ranking")
def get_sentiment_ranking(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(args.get("sentiment_type") or "negative").lower()
    if kind not in ("negative", "positive"):
        kind = "negative"
    return sentiment_ranking(
        state.network,
        kind=kind,
        entity_type=args.get("entity_type"),
        limit=_as_int(args.get("limit"), 5),
    )


# --- 10. kontrafaktual -----------------------------------------------------


@tool("simulate_what_if_scenario")
def simulate_what_if_scenario(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    result = simulate_removal(state.network, str(args.get("target_node", "")))
    result["status"] = "ready" if result.get("success") else str(result.get("reason"))
    return result


# --- 11. kendali kanvas ----------------------------------------------------


@tool("direct_canvas_view")
def direct_canvas_view(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    action = str(args.get("action") or "RESET_VIEW").upper()
    if action not in CANVAS_ACTIONS:
        return {
            "status": "invalid_action",
            "message": f"Aksi '{action}' tidak dikenal.",
            "available_actions": list(CANVAS_ACTIONS),
        }

    command: Dict[str, Any] = {"action": action}

    if action in ("FOCUS_NODE", "TRIGGER_TRACE"):
        nodes = _as_list(args.get("target_nodes"))
        if not nodes:
            return {"status": "missing_argument", "message": "target_nodes wajib diisi."}
        resolved = [_entity(state, name) for name in nodes]
        command["node_id"] = resolved[0]
        if action == "TRIGGER_TRACE":
            if len(resolved) < 2:
                return {
                    "status": "missing_argument",
                    "message": "TRIGGER_TRACE memerlukan dua entitas: asal dan tujuan.",
                }
            command["path"] = [resolved[0], resolved[-1]]
        command["scale"] = 1.2
        return {"status": "ready", **command}

    if action == "ISOLATE_CLUSTER":
        cluster = str(args.get("cluster_name") or "").strip()
        if not cluster:
            return {"status": "missing_argument", "message": "cluster_name wajib diisi."}
        command["cluster"] = cluster
        return {"status": "ready", **command}

    if action == "COMPARE_NODES":
        nodes = _as_list(args.get("target_nodes"))
        if len(nodes) < 2:
            return {"status": "missing_argument", "message": "COMPARE_NODES butuh dua entitas."}
        command["nodes"] = [_entity(state, name) for name in nodes[:2]]
        return {"status": "ready", **command}

    return {"status": "ready", **command}


# --- 12. briefing ----------------------------------------------------------


@tool("generate_executive_briefing")
def generate_executive_briefing(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    result = executive_briefing(
        state.network,
        temporal=state.temporal,
        anomaly=state.anomaly,
        bipartite=state.bipartite,
    )
    result["status"] = "ready"
    result["title"] = state.presentation.title
    result["centre"] = centre_label(state)
    return result


# --- 13. lubang struktural -------------------------------------------------


@tool("get_structural_holes_ranking")
def get_structural_holes_ranking(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(args.get("mode") or "high_autonomy")
    if mode not in ("high_autonomy", "high_constraint"):
        mode = "high_autonomy"
    result = structural_holes(state.network, mode=mode, limit=_as_int(args.get("limit"), 10))
    return {"status": "ready", **result}


# --- 14. lintasan ----------------------------------------------------------


@tool("get_entity_temporal_trajectory")
def get_entity_temporal_trajectory(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    entity_id = _entity(state, args.get("entity_name"))
    dossier = entity_dossier(state.network, entity_id, temporal=state.temporal)
    return {
        "status": "ready",
        "id": dossier["id"],
        "label": dossier["label"],
        "entity_type": dossier["entity_type"],
        "trajectory": dossier["trajectory"],
        "exposure": dossier["exposure"],
    }


# --- 15. topik -------------------------------------------------------------


@tool("get_topic_actor_network")
def get_topic_actor_network(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    result = queries.topic_actor_network(
        state,
        topic=args.get("topic_filter"),
        min_npmi=_as_float(args.get("min_npmi"), 0.0),
    )
    result["status"] = "ready" if result["edges"] else "empty"
    return result


# --- 16. perbandingan epos -------------------------------------------------


@tool("compare_network_periods")
def compare_network_periods(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    ids = specs.epoch_ids(state)
    if len(ids) < 2:
        return {
            "status": "unavailable",
            "message": "Perlu minimal dua epos untuk membandingkan.",
            "available_epochs": ids,
        }

    baseline = str(args.get("baseline_period") or ids[0])
    target = str(args.get("target_period") or ids[-1])
    if baseline not in ids or target not in ids:
        return {
            "status": "invalid_argument",
            "message": f"Epos tidak dikenal. Pilihan: {', '.join(ids)}",
            "available_epochs": ids,
        }

    result = queries.compare_epochs(
        state.temporal.by_id(baseline), state.temporal.by_id(target)
    )
    # Daftar per simpul dipakai tabel UI, bukan model: 77 baris lengkap menghabiskan
    # konteks untuk informasi yang sudah terwakili di top_gainers/top_losers.
    result.pop("nodes", None)
    result["status"] = "ready"
    return result


# --- 17. bukti tepi --------------------------------------------------------


@tool("get_edge_evidence")
def get_edge_evidence(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    source = _entity(state, args.get("source"))
    target = _entity(state, args.get("target"))
    if not state.network.graph.has_edge(source, target):
        return {
            "status": "not_found",
            "message": "Tepi tidak ada di jaringan.",
            "source": source,
            "target": target,
        }

    data = state.network.graph.edges[source, target]
    return {
        "status": "ready",
        "source": source,
        "target": target,
        "weight": int(data.get("weight", 0)),
        "npmi": _num(data.get("npmi")),
        "rescued": bool(data.get("rescued", False)),
        "evidence": queries.shared_articles(
            state, source, target, _as_int(args.get("limit"), 5)
        ),
    }


# --- 18. katalog -----------------------------------------------------------


@tool("list_entities")
def list_entities(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    frame = state.network.node_metrics
    if frame.empty:
        return {"status": "empty", "entities": []}

    entity_type = args.get("entity_type")
    if entity_type:
        keep = [
            entity_id
            for entity_id in frame.index
            if (state.network.type_of(entity_id) or "").lower() == str(entity_type).lower()
        ]
        frame = frame.loc[keep]
        if frame.empty:
            return {
                "status": "empty",
                "message": f"Tidak ada entitas bertipe '{entity_type}'.",
                "available_types": list(state.presentation.entity_types),
                "entities": [],
            }

    order = str(args.get("order") or "degree")
    if order not in ("degree", "betweenness", "constraint", "articles"):
        order = "degree"
    column = "burt_constraint" if order == "constraint" else order
    ascending = order == "constraint"
    ordered = frame.sort_values([column, "entity_id"], ascending=[ascending, True])
    limit = _as_int(args.get("limit"), 20)

    return {
        "status": "ready",
        "order": order,
        "count": int(len(frame)),
        "name_coverage": unresolved_share(state.network),
        "entities": [
            {
                "id": str(entity_id),
                "label": state.network.label_of(entity_id),
                "entity_type": state.network.type_of(entity_id),
                "degree": int(row["degree"]),
                "betweenness": _num(row["betweenness"]),
                "constraint": _num(row["burt_constraint"]),
                "articles": int(row["articles"]),
            }
            for entity_id, row in ordered.head(max(0, limit)).iterrows()
        ],
    }


# --- 19. anomali -----------------------------------------------------------


@tool("get_anomaly_report")
def get_anomaly_report(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    report = state.anomaly
    if not report.spikes:
        return {
            "status": "empty",
            "message": state.presentation.text("empty_anomaly", "Belum ada anomali."),
            "months": report.months,
            "spikes": [],
        }
    return {
        "status": "ready",
        "months": report.months,
        "partial_periods": list(report.partial_periods),
        "spikes": [
            {
                "period": spike.get("period"),
                "article_count": spike.get("article_count"),
                "z_score": _num(spike.get("z_score")),
                "severity": spike.get("severity"),
            }
            for spike in report.spikes
        ],
    }


# --- 20. glosarium ---------------------------------------------------------


@tool("get_glossary")
def get_glossary(state: AppState, args: Dict[str, Any]) -> Dict[str, Any]:
    term = str(args.get("term") or "").strip().lower()
    if not term:
        return {"status": "ready", "terms": sorted(GLOSSARY)}

    resolved = _match_term(term)
    if resolved is None:
        return {
            "status": "not_found",
            "message": f"Istilah '{term}' tidak ada di glosarium.",
            "terms": sorted(GLOSSARY),
        }
    return {"status": "ready", "term": resolved, "definition": GLOSSARY[resolved]}


def _match_term(term: str) -> Optional[str]:
    """Cocokkan kata pertama yang dikenal, supaya 'constraint burt' tidak ambigu."""
    if term in GLOSSARY:
        return term
    for word in term.replace("-", " ").split():
        if word in GLOSSARY:
            return word
        candidates = sorted(key for key in GLOSSARY if word in key or key in word)
        if len(candidates) == 1:
            return candidates[0]
    return None


def execute(state: AppState, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Jalankan satu tool; kegagalan dikembalikan sebagai status, bukan exception."""
    handler = _DISPATCH.get(name)
    if handler is None:
        return {
            "status": "unknown_tool",
            "message": f"Tool '{name}' tidak dikenal.",
            "available_tools": sorted(_DISPATCH),
        }
    try:
        return handler(state, arguments or {})
    except KeyError as exc:
        return {"status": "not_found", "message": str(exc).strip("'\"")}
    except Exception as exc:  # noqa: BLE001 - dilaporkan ke model, bukan ditelan
        return {"status": "error", "message": f"{type(exc).__name__}: {exc}"}


def tool_names() -> List[str]:
    return sorted(_DISPATCH)


# --- kecil -----------------------------------------------------------------


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value if str(item).strip()]


def _num(value: Any) -> Optional[float]:
    return to_number(value, 6)

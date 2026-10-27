"""
Jawaban deterministik tanpa LLM.

Kalimatnya tidak ditulis di file ini: setiap jawaban dirakit dari template di
`Presentation.wording` (lihat `DEFAULT_WORDING` di `presentation.py`), lalu
diisi angka dari tool yang sama dengan yang dipakai agen LLM. Bundle boleh
mengganti kalimatnya tanpa menyentuh kode.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .._coerce import to_number
from ..api.state import AppState
from . import intent as intent_mod
from . import tools
from .prompt import centre_label


def answer(state: AppState, query: str) -> Dict[str, Any]:
    """Jawaban deterministik untuk satu pertanyaan; tidak pernah melempar."""
    intent = intent_mod.classify(query)
    entities = intent_mod.find_entities(state, query)
    agent = intent_mod.agent_for(intent)

    try:
        text, command = _compose(state, intent, entities, query)
    except Exception as exc:  # noqa: BLE001 - fallback terakhir tidak boleh gagal
        text = f"Data untuk pertanyaan ini belum bisa disusun ({type(exc).__name__})."
        command = None

    return {
        "agent": agent,
        "text": text,
        "canvas_command": command,
        "tools_called": [],
        "fallback": True,
        "intent": intent,
    }


def _compose(
    state: AppState, intent: str, entities: List[str], query: str
) -> tuple[str, Optional[Dict[str, Any]]]:
    handler = _HANDLERS.get(intent, _unknown)
    return handler(state, entities, query)


def _text(state: AppState, key: str, **values: Any) -> str:
    template = state.presentation.text(key, "")
    if not template:
        return ""
    return template.format(**values)


def _articles_label(state: AppState) -> str:
    return state.presentation.label("articles", "artikel")


def _greeting(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    summary = state.network.summary
    return (
        _text(
            state,
            "fallback_greeting",
            title=state.presentation.title,
            nodes=summary.get("nodes"),
            edges=summary.get("edges"),
        ),
        None,
    )


def _overview(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    summary = state.network.summary
    communities = summary.get("communities") or {}
    year_span = state.temporal.year_span
    return (
        _text(
            state,
            "fallback_overview",
            title=state.presentation.title,
            nodes=summary.get("nodes"),
            edges=summary.get("edges"),
            density=summary.get("density"),
            communities=communities.get("count"),
            modularity=communities.get("modularity"),
            articles=state.network.total_articles,
            articles_label=_articles_label(state),
            year_start=year_span[0],
            year_end=year_span[1],
        ),
        None,
    )


def _dossier(state: AppState, entities: List[str], query: str) -> tuple[str, Optional[Dict[str, Any]]]:
    if not entities:
        return _overview(state, entities, query)

    dossier = tools.execute(state, "get_entity_dossier", {"entity_name": entities[0]})
    if dossier.get("status") != "ready":
        return _overview(state, entities, query)

    text = _text(
        state,
        "fallback_dossier",
        label=dossier["label"],
        entity_type=dossier.get("entity_type") or "-",
        degree=dossier["degree"],
        betweenness=_num(dossier.get("betweenness")),
        constraint=_num(dossier.get("burt_constraint")),
        articles=dossier["articles"],
        articles_label=_articles_label(state),
    )
    command = {"action": "CANVAS_FOCUS", "node_id": dossier["id"], "scale": 1.2}
    return text, command


def _broker(state: AppState, entities: List[str], query: str) -> tuple[str, Optional[Dict[str, Any]]]:
    result = tools.execute(state, "get_broker_ranking", {"limit": 5})
    ranking = result.get("ranking") or []
    if not ranking:
        return _overview(state, entities, query)
    items = ", ".join(
        f"{row['label']} ({_num(row['betweenness'])})" for row in ranking[:5]
    )
    command = {"action": "CANVAS_FOCUS", "node_id": ranking[0]["id"], "scale": 1.2}
    return _text(state, "fallback_broker", items=items), command


def _holes(state: AppState, entities: List[str], query: str) -> tuple[str, Optional[Dict[str, Any]]]:
    result = tools.execute(state, "get_structural_holes_ranking", {"mode": "high_autonomy"})
    ranking = result.get("ranking") or []
    if not ranking:
        return _overview(state, entities, query)
    items = ", ".join(
        f"{row['label']} (C={_num(row['burt_constraint'])})" for row in ranking[:5]
    )
    command = {"action": "CANVAS_FOCUS", "node_id": ranking[0]["id"], "scale": 1.2}
    return _text(state, "fallback_holes", items=items), command


def _path(state: AppState, entities: List[str], query: str) -> tuple[str, Optional[Dict[str, Any]]]:
    if len(entities) < 2:
        examples = _example_entities(state)
        return (
            _text(
                state,
                "fallback_path_missing",
                example_a=examples[0],
                example_b=examples[1],
            ),
            None,
        )

    result = tools.execute(
        state, "trace_causal_path", {"origin": entities[0], "target": entities[1]}
    )
    if not result.get("success"):
        return (
            _text(
                state,
                "fallback_path_none",
                origin=state.network.label_of(entities[0]),
                target=state.network.label_of(entities[1]),
            ),
            None,
        )

    labels = [state.network.label_of(node) for node in result["path"]]
    command = {"action": "HIGHLIGHT_PATH", "path": result["path"], "focus_target": result["path"][-1]}
    return (
        _text(
            state,
            "fallback_path",
            origin=labels[0],
            target=labels[-1],
            path=" -> ".join(labels),
            hops=result["total_hops"],
            weight=result["total_weight"],
        ),
        command,
    )


def _sentiment(state: AppState, entities: List[str], query: str) -> tuple[str, Optional[Dict[str, Any]]]:
    result = tools.execute(state, "get_sentiment_ranking", {"sentiment_type": "negative"})
    if result.get("status") != "ready" or not result.get("ranking"):
        return _text(state, "fallback_sentiment_awaiting"), None

    items = ", ".join(
        f"{row['label']} ({_num(row['neg'])}%)" for row in result["ranking"][:5]
    )
    command = {"action": "CANVAS_FOCUS", "node_id": result["ranking"][0]["id"], "scale": 1.15}
    return _text(state, "fallback_sentiment", kind="negatif", items=items), command


def _whatif(state: AppState, entities: List[str], query: str) -> tuple[str, Optional[Dict[str, Any]]]:
    if not entities:
        return _overview(state, entities, query)

    result = tools.execute(state, "simulate_what_if_scenario", {"target_node": entities[0]})
    if result.get("status") == "ego_protected":
        return (
            _text(state, "fallback_whatif_protected", label=state.network.label_of(entities[0])),
            None,
        )
    if not result.get("success"):
        return _overview(state, entities, query)

    return (
        _text(
            state,
            "fallback_whatif",
            label=result["removed"]["label"],
            delta=_num(result["delta_density"]),
            lost_edges=result["lost_edges"],
            isolated=len(result["isolated_nodes"]),
        ),
        {"action": "CANVAS_FOCUS", "node_id": result["removed"]["id"], "scale": 1.2},
    )


def _briefing(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    result = tools.execute(state, "generate_executive_briefing", {})
    macro = result["macro"]
    broker = result.get("critical_broker") or {}
    lines = [
        _text(
            state,
            "fallback_overview",
            title=state.presentation.title,
            nodes=macro["nodes"],
            edges=macro["edges"],
            density=macro["density"],
            communities=macro["communities"],
            modularity=macro["modularity"],
            articles=macro["articles"],
            articles_label=_articles_label(state),
            year_start=state.temporal.year_span[0],
            year_end=state.temporal.year_span[1],
        )
    ]
    if broker:
        lines.append(
            _text(
                state,
                "fallback_broker",
                items=f"{broker['label']} ({_num(broker['betweenness'])})",
            )
        )
    lines.append(_anomaly_line(state))
    return "\n\n".join(line for line in lines if line), None


def _anomaly(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    return _anomaly_line(state), None


def _anomaly_line(state: AppState) -> str:
    result = tools.execute(state, "get_anomaly_report", {})
    spikes = result.get("spikes") or []
    if not spikes:
        return state.presentation.text("fallback_anomaly_none", "")
    items = ", ".join(
        f"{spike['period']} ({spike['article_count']})" for spike in spikes[:5]
    )
    return _text(
        state, "fallback_anomaly", items=items, articles_label=_articles_label(state)
    )


def _topic(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    result = tools.execute(state, "get_topic_actor_network", {})
    summary = result.get("summary") or {}
    return (
        _text(
            state,
            "fallback_topic",
            topics=summary.get("topics"),
            actors=summary.get("actors"),
            edges=summary.get("edges"),
        ),
        None,
    )


def _compare(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    result = tools.execute(state, "compare_network_periods", {})
    if result.get("status") != "ready":
        return result.get("message", ""), None
    return (
        _text(
            state,
            "fallback_compare",
            baseline=result["baseline_period"],
            target=result["target_period"],
            gained=result["gained_count"],
            lost=result["lost_count"],
            persisted=result["persisted_count"],
        ),
        None,
    )


def _corpus(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    return _unknown(state, entities, query)


def _glossary(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    term = _glossary_term(query)
    result = tools.execute(state, "get_glossary", {"term": term})
    if result.get("status") == "ready" and result.get("definition"):
        return f"{result['term']}: {result['definition']}", None
    terms = result.get("terms") or []
    return "Istilah yang tersedia: " + ", ".join(terms), None


def _glossary_term(query: str) -> str:
    text = (query or "").lower()
    for prefix in ("apa itu", "apa yang dimaksud", "definisi", "arti istilah", "maksud istilah"):
        text = text.replace(prefix, " ")
    words = [word for word in re.split(r"[^a-z0-9_]+", text) if len(word) >= 3]
    return " ".join(words)


def _canvas(state: AppState, entities: List[str], query: str) -> tuple[str, Optional[Dict[str, Any]]]:
    if not entities:
        return _overview(state, entities, query)
    return (
        f"Sorotan diarahkan ke {state.network.label_of(entities[0])}.",
        {"action": "CANVAS_FOCUS", "node_id": entities[0], "scale": 1.2},
    )


def _casual(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    return _overview(state, entities, query)


def _unknown(state: AppState, entities: List[str], query: str) -> tuple[str, None]:
    examples = _example_prompts(state)
    return _text(state, "fallback_unknown", examples=" | ".join(examples)), None


def _example_entities(state: AppState) -> tuple[str, str]:
    """Dua nama entitas nyata untuk contoh di pesan bantuan."""
    ranked = tools.execute(state, "list_entities", {"limit": 2}).get("entities") or []
    labels = [row["label"] for row in ranked]
    centre = centre_label(state)
    first = labels[0] if labels else centre
    second = labels[1] if len(labels) > 1 else centre
    return first, second


def _example_prompts(state: AppState) -> List[str]:
    """Contoh pertanyaan dari metadata; jatuh ke kosakata struktural bila kosong."""
    wording = state.presentation.wording
    centre = centre_label(state)
    candidates = [
        wording.get("chip_summary"),
        wording.get("chip_broker"),
        wording.get("chip_risk"),
        wording.get("chip_memo"),
    ]
    filled = [
        value.format(label=centre, centre=centre, articles=_articles_label(state))
        for value in candidates
        if value
    ]
    return filled[:3] or [
        "Ringkas topologi jaringan",
        "Siapa broker teratas?",
        "Buatkan memo eksekutif",
    ]


def _num(value: Any) -> Optional[float]:
    return to_number(value, 4)


_HANDLERS = {
    "greeting": _greeting,
    "casual": _casual,
    "overview": _overview,
    "dossier": _dossier,
    "path": _path,
    "broker": _broker,
    "holes": _holes,
    "sentiment": _sentiment,
    "whatif": _whatif,
    "briefing": _briefing,
    "topic": _topic,
    "compare": _compare,
    "anomaly": _anomaly,
    "corpus": _corpus,
    "canvas": _canvas,
    "glossary": _glossary,
    "unknown": _unknown,
}

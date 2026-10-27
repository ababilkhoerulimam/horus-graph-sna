"""
Prompt copilot, dirakit dari data.

Tidak ada nama domain di file ini. Judul, label pusat, tipe entitas, epos, dan
contoh entitas semuanya dibaca dari `Presentation` dan `NetworkBundle`, sehingga
repo yang di-fork dengan bundle lain otomatis mendapat persona yang berbeda.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..api.state import AppState

MAX_EXAMPLE_ENTITIES = 6


def centre_label(state: AppState) -> str:
    """Nama pusat jaringan, atau penanda eksplisit bila dataset tanpa pusat."""
    ego = state.presentation.ego
    if ego is None:
        return "tanpa pusat"
    return ego.label or ego.id


def has_centre(state: AppState) -> bool:
    return state.presentation.ego is not None


def top_entities(state: AppState, limit: int = MAX_EXAMPLE_ENTITIES) -> List[Dict[str, Any]]:
    """
    Entitas berderajat tertinggi, satu per tipe lebih dulu.

    Satu per tipe dipakai supaya contoh pertanyaan tidak menumpuk pada satu
    jenis entitas ketika satu tipe mendominasi katalog.
    """
    frame = state.network.node_metrics
    if frame.empty:
        return []

    ordered = frame.sort_values(["degree", "entity_id"], ascending=[False, True])
    picked: List[Dict[str, Any]] = []
    seen_types: set[str] = set()

    for entity_id, row in ordered.iterrows():
        entity_type = state.network.type_of(entity_id) or ""
        if entity_type in seen_types and len(picked) < limit:
            continue
        seen_types.add(entity_type)
        picked.append(
            {
                "id": str(entity_id),
                "label": state.network.label_of(entity_id),
                "entity_type": entity_type,
                "degree": int(row["degree"]),
            }
        )
        if len(picked) >= limit:
            break

    if len(picked) < limit:
        for entity_id, row in ordered.iterrows():
            if any(item["id"] == str(entity_id) for item in picked):
                continue
            picked.append(
                {
                    "id": str(entity_id),
                    "label": state.network.label_of(entity_id),
                    "entity_type": state.network.type_of(entity_id) or "",
                    "degree": int(row["degree"]),
                }
            )
            if len(picked) >= limit:
                break

    return picked[:limit]


def epochs_summary(state: AppState) -> List[str]:
    lines = []
    for slice_ in state.temporal.slices:
        if slice_.window.id == "all_time":
            continue
        narrative = state.presentation.epoch_narratives.get(slice_.window.id, "")
        suffix = f" - {narrative}" if narrative else ""
        lines.append(
            f"- {slice_.window.id}: {slice_.window.label} "
            f"({slice_.window.start_year}-{slice_.window.end_year}, "
            f"{slice_.graph.number_of_nodes()} simpul){suffix}"
        )
    return lines


def build_persona(state: AppState) -> str:
    """System prompt yang menyebut angka nyata, bukan placeholder."""
    presentation = state.presentation
    network = state.network
    summary = network.summary
    centre = centre_label(state)

    types = ", ".join(
        f"{style.label or style.id} ({style.id})"
        for style in presentation.entity_types.values()
    ) or "tidak dideklarasikan"

    year_span = state.temporal.year_span
    span = (
        f"{year_span[0]}-{year_span[1]}"
        if year_span and year_span[1]
        else "rentang tidak diketahui"
    )

    entity_lines = [
        f"- {item['label']} ({item['entity_type'] or 'tanpa tipe'}, {item['degree']} relasi)"
        for item in top_entities(state)
    ]

    blocks = [
        f"Anda adalah analis jaringan pada dataset \"{presentation.title}\".",
        presentation.subtitle or "",
        "",
        "## Cakupan data",
        f"- Pusat jaringan: {centre}",
        f"- Korpus: {network.total_articles} {presentation.label('articles', 'artikel')}",
        f"- Graf: {summary.get('nodes')} simpul, {summary.get('edges')} sisi, "
        f"kepadatan {summary.get('density')}",
        f"- Komunitas: {(summary.get('communities') or {}).get('count')} "
        f"(modularitas {(summary.get('communities') or {}).get('modularity')})",
        f"- Rentang tahun: {span}",
        f"- Tipe entitas: {types}",
    ]

    epoch_lines = epochs_summary(state)
    if epoch_lines:
        blocks.append("- Epos: ")
        blocks.extend("  " + line for line in epoch_lines)

    if entity_lines:
        blocks.append("")
        blocks.append("## Entitas paling terhubung (contoh, bukan peringkat resmi)")
        blocks.extend(entity_lines)

    layers = dict(network.layers)
    awaiting = [name for name, status in layers.items() if status != "ready"]
    if awaiting:
        blocks.append("")
        blocks.append(
            "## Lapisan belum tersedia: " + ", ".join(awaiting) + ". "
            "Bila ditanya soal lapisan ini, sampaikan bahwa datanya belum ada."
        )

    blocks.append("")
    blocks.append("## Aturan")
    blocks.append(
        "- DILARANG MENGARANG ANGKA. Setiap sentralitas, derajat, constraint, "
        "lead time, dan jumlah artikel harus berasal dari hasil pemanggilan tool."
    )
    blocks.append(
        "- Bila tool mengembalikan status selain `ready` (misalnya `awaiting_input`), "
        "laporkan apa adanya. Jangan menebak, dan jangan menampilkan 0 sebagai hasil ukur."
    )
    blocks.append("- Panggil tool yang relevan sebelum menyimpulkan.")
    blocks.append(
        "- Jawab dalam bahasa yang dipakai pengguna, ringkas, dan berbasis bukti. "
        "Markdown dipakai hanya bila membantu keterbacaan."
    )
    blocks.append(
        "- DILARANG memakai em dash maupun en dash. Gunakan koma, titik dua, "
        "tanda kurung, atau tanda hubung biasa (-)."
    )
    if presentation.action_rules:
        blocks.append(
            "- Saat menilai peran satu entitas, gunakan ambang yang sudah ada di "
            "sistem (broker, dependen, seimbang) alih-alih membuat kategori baru."
        )

    return "\n".join(line for line in blocks if line is not None)


def build_examples(state: AppState) -> Dict[str, List[str]]:
    """
    Empat blok contoh pertanyaan.

    Dipakai untuk menyusun petunjuk di prompt dan untuk menguji bahwa kosakata
    yang muncul memang berasal dari metadata bundle, bukan dari kode.
    """
    centre = centre_label(state)
    entities = top_entities(state, limit=3)
    first = entities[0]["label"] if entities else centre
    second = entities[1]["label"] if len(entities) > 1 else centre
    labels = state.presentation.labels
    articles = labels.get("articles", "artikel")

    return {
        "profil": [
            f"Apa peran {first} dalam jaringan?",
            f"Bagaimana lintasan {second} antar-epos?",
        ],
        "struktur": [
            "Siapa simpul dengan betweenness tertinggi?",
            "Siapa yang punya constraint Burt terendah?",
            f"Bagaimana jalur dari {first} ke {centre}?",
        ],
        "risiko": [
            f"Bagaimana jika {first} keluar dari jaringan?",
            "Bulan mana yang jumlah " + articles + "nya melonjak?",
        ],
        "sintesis": [
            f"Ringkas topologi {centre}",
            "Buatkan memo eksekutif",
        ],
    }


def example_lines(state: AppState) -> str:
    blocks = build_examples(state)
    lines = []
    for name, questions in blocks.items():
        lines.append(f"- {name}: " + " | ".join(questions))
    return "\n".join(lines)

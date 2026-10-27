"""
Ekspor jaringan ke format yang dibaca alat lain.

Tiga format, satu aturan: **angka yang tidak terukur tidak ditulis**. Node tanpa
betweenness (misalnya karena tidak ada jalur yang melewatinya) tidak mendapat
`<data>` untuk atribut itu, bukan `0`. Kalau alat tujuan mengisi nol sendiri,
itu keputusannya — bukan keputusan kita yang menyamarkan ketiadaan.

Ditulis dengan pustaka standar (`xml.sax.saxutils`) supaya tidak ada dependensi
baru hanya untuk mencetak XML.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

from ..core.build import NetworkBundle

# Atribut simpul yang diekspor. Urutan ini juga urutan kolom di GEXF, jadi
# kolom Gephi stabil antar ekspor.
NODE_ATTRS: Tuple[Tuple[str, str], ...] = (
    ("label", "string"),
    ("entity_type", "string"),
    ("articles", "long"),
    ("degree", "long"),
    ("pagerank", "double"),
    ("betweenness", "double"),
    ("closeness", "double"),
    ("burt_constraint", "double"),
    ("effective_size", "double"),
    ("structural_hole_role", "string"),
    ("louvain_community", "long"),
)

EDGE_ATTRS: Tuple[Tuple[str, str], ...] = (
    ("weight", "long"),
    ("npmi", "double"),
    ("rescued", "boolean"),
)

FORMATS = ("graphml", "gexf", "csv")

CONTENT_TYPES = {
    "graphml": "application/graphml+xml",
    "gexf": "application/gexf+xml",
    "csv": "text/csv",
}

EXTENSIONS = {"graphml": "graphml", "gexf": "gexf", "csv": "csv"}


def _clean(value: Any) -> Optional[Any]:
    """Buang nilai yang tidak bisa dipercaya sebagai angka.

    `NaN` dan `inf` bukan angka yang bisa dibaca alat lain, dan `None` berarti
    tidak terukur. Ketiganya hilang dari keluaran.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if hasattr(value, "item"):  # numpy scalar
        return _clean(value.item())
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _node_rows(network: NetworkBundle) -> List[Tuple[str, Dict[str, Any]]]:
    # `entities` di-index oleh entity_id, bukan memuat kolom entity_id.
    entities = network.entities
    labels = entities["label"].to_dict() if "label" in entities.columns else {}
    types = entities["entity_type"].to_dict() if "entity_type" in entities.columns else {}
    metrics = network.node_metrics

    rows: List[Tuple[str, Dict[str, Any]]] = []
    for node_id in sorted(network.graph.nodes, key=str):
        record: Dict[str, Any] = {
            "label": labels.get(node_id) or str(node_id),
            "entity_type": types.get(node_id),
        }
        if node_id in metrics.index:
            series = metrics.loc[node_id]
            for column in (
                "articles",
                "degree",
                "pagerank",
                "betweenness",
                "closeness",
                "burt_constraint",
                "effective_size",
                "structural_hole_role",
                "louvain_community",
            ):
                if column in series.index:
                    record[column] = series[column]
        rows.append((str(node_id), record))
    return rows


def _edge_rows(network: NetworkBundle) -> List[Tuple[str, str, Dict[str, Any]]]:
    rows = []
    for source, target, data in network.graph.edges(data=True):
        a, b = sorted((str(source), str(target)))
        rows.append((a, b, dict(data)))
    rows.sort(key=lambda item: (item[0], item[1]))
    return rows


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def to_graphml(network: NetworkBundle) -> str:
    """GraphML 1.0, tanpa namespace tambahan agar dibaca Gephi dan igraph."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
    ]
    for name, kind in NODE_ATTRS:
        lines.append(f'  <key id="{name}" for="node" attr.name="{name}" attr.type="{kind}"/>')
    for name, kind in EDGE_ATTRS:
        lines.append(f'  <key id="{name}" for="edge" attr.name="{name}" attr.type="{kind}"/>')
    lines.append('  <graph id="horus" edgedefault="undirected">')

    for node_id, record in _node_rows(network):
        lines.append(f"    <node id={quoteattr(node_id)}>")
        for name, _kind in NODE_ATTRS:
            value = _clean(record.get(name))
            if value is None:
                continue
            lines.append(f'      <data key="{name}">{escape(_fmt(value))}</data>')
        lines.append("    </node>")

    for index, (source, target, data) in enumerate(_edge_rows(network)):
        lines.append(
            f"    <edge id=\"e{index}\" source={quoteattr(source)} target={quoteattr(target)}>"
        )
        for name, _kind in EDGE_ATTRS:
            value = _clean(data.get(name))
            if value is None:
                continue
            lines.append(f'      <data key="{name}">{escape(_fmt(value))}</data>')
        lines.append("    </edge>")

    lines.append("  </graph>")
    lines.append("</graphml>")
    return "\n".join(lines) + "\n"


def to_gexf(network: NetworkBundle) -> str:
    """GEXF 1.2. `defaultedgetype="undirected"` karena co-occurrence simetris."""
    node_attrs = [(name, kind) for name, kind in NODE_ATTRS if name not in ("label",)]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gexf xmlns="http://gexf.net/1.2" version="1.2">',
        '  <graph mode="static" defaultedgetype="undirected">',
        '    <attributes class="node">',
    ]
    for name, kind in node_attrs:
        gexf_type = {"string": "string", "long": "long", "double": "double", "boolean": "boolean"}[kind]
        lines.append(f'      <attribute id="{name}" title="{name}" type="{gexf_type}"/>')
    lines.append("    </attributes>")
    lines.append("    <nodes>")

    for node_id, record in _node_rows(network):
        lines.append(f"      <node id={quoteattr(node_id)} label={quoteattr(str(record.get('label') or node_id))}>")
        values = []
        for name, _kind in node_attrs:
            value = _clean(record.get(name))
            if value is None:
                continue
            values.append(f'<attvalue for="{name}" value={quoteattr(_fmt(value))}/>')
        if values:
            lines.append("        <attvalues>" + "".join(values) + "</attvalues>")
        lines.append("      </node>")

    lines.append("    </nodes>")
    lines.append("    <edges>")
    for index, (source, target, data) in enumerate(_edge_rows(network)):
        weight = _clean(data.get("weight"))
        weight_attr = f' weight="{_fmt(weight)}"' if weight is not None else ""
        lines.append(
            f"      <edge id=\"e{index}\" source={quoteattr(source)} "
            f"target={quoteattr(target)}{weight_attr}>"
        )
        values = []
        for name, _kind in EDGE_ATTRS:
            if name == "weight":
                continue
            value = _clean(data.get(name))
            if value is None:
                continue
            values.append(f'<attvalue for="{name}" value={quoteattr(_fmt(value))}/>')
        if values:
            lines.append("        <attvalues>" + "".join(values) + "</attvalues>")
        lines.append("      </edge>")

    lines.append("    </edges>")
    lines.append("  </graph>")
    lines.append("</gexf>")
    return "\n".join(lines) + "\n"


def to_csv(network: NetworkBundle) -> str:
    """Daftar sisi. Metrik simpul ada di GraphML/GEXF, bukan di sini."""
    lines = ["source,target,weight,npmi,rescued"]
    for source, target, data in _edge_rows(network):
        cells = [
            _csv_cell(source),
            _csv_cell(target),
            _cell(data.get("weight")),
            _cell(data.get("npmi")),
            _fmt(bool(data.get("rescued", False))),
        ]
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def _cell(value: Any) -> str:
    """Sel kosong untuk nilai yang tidak terukur, bukan `0`."""
    cleaned = _clean(value)
    return "" if cleaned is None else _fmt(cleaned)


def _csv_cell(value: str) -> str:
    text = str(value)
    if any(char in text for char in ',"\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def render(network: NetworkBundle, fmt: str) -> str:
    renderer = {"graphml": to_graphml, "gexf": to_gexf, "csv": to_csv}.get(fmt)
    if renderer is None:
        raise ValueError(f"Format tidak dikenal: {fmt}. Pilihan: {', '.join(FORMATS)}")
    return renderer(network)

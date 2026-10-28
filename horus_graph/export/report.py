"""
Laporan HTML mandiri.

Tujuan berkas ini: satu temuan bisa diserahkan sebagai satu berkas yang bisa
dibuka tanpa server, tanpa internet, dan tanpa menjelaskan apa pun secara
lisan. Karena itu laporannya memuat tiga hal yang sering hilang saat angka
dipindahkan ke slide: **dari snapshot mana** angka itu berasal, **pada ambang
apa** ia dihitung, dan **apa yang tidak bisa disimpulkan** darinya.

Tidak ada dependensi baru dan tidak ada aset eksternal: CSS ditulis di dalam,
gambar ikut sebagai SVG sebaris. Berkas yang dihasilkan tetap terbaca setelah
server dimatikan, setelah bundle dipindah, dan setelah versi engine berubah.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from ..annotations import Annotation
from .svg_sanitize import sanitize_svg

LIMITATIONS_HEADING = "Apa yang tidak bisa disimpulkan dari laporan ini"

# Ditaruh di laporan, bukan hanya di penyaring: CSP berlaku juga saat berkas
# dibuka lewat file://, dan menutup lubang penyaring yang belum ditemukan.
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"


def render_report(
    *,
    provenance: Dict[str, Any],
    annotations: Optional[List[Annotation]] = None,
    svg: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None,
    title: str = "Laporan Analisis Jaringan",
) -> str:
    contract = provenance.get("contract") or {}
    parameters = provenance.get("parameters") or {}
    population = provenance.get("population") or {}
    software = provenance.get("software") or {}
    metrics = provenance.get("metrics") or {}
    limitations = provenance.get("limitations") or []
    inference = provenance.get("inference") or {}

    snapshot = contract.get("dataset_id") or "tanpa nama"
    subtitle = (
        f"{_text(snapshot)} &middot; kontrak {_text(contract.get('version'))} "
        f"&middot; {_text(_range_text(contract))}"
    )

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<title>{_text(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 32px; background: #F8FAFC; color: #0F172A;
         font: 14px/1.55 "Segoe UI", system-ui, -apple-system, sans-serif; }}
  main {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 13px; letter-spacing: .08em; text-transform: uppercase;
        color: #475569; margin: 28px 0 10px; }}
  .sub {{ color: #475569; font-size: 12px; margin-bottom: 20px; }}
  .card {{ background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px;
           padding: 14px 16px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }}
  .kv {{ font-size: 12px; }}
  .kv dt {{ color: #64748B; margin: 0; }}
  .kv dd {{ margin: 0 0 8px; font-weight: 700; font-variant-numeric: tabular-nums; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #E2E8F0;
            font-variant-numeric: tabular-nums; }}
  th {{ color: #64748B; font-weight: 600; }}
  ul {{ margin: 0; padding-left: 18px; }}
  li {{ margin-bottom: 4px; }}
  .note {{ border-left: 3px solid #0EA5E9; padding: 8px 12px; background: #F1F5F9;
           border-radius: 0 6px 6px 0; margin-bottom: 8px; }}
  .note-meta {{ color: #64748B; font-size: 11px; }}
  .figure {{ background: #0B1220; border-radius: 8px; padding: 8px; overflow: hidden; }}
  .figure svg {{ width: 100%; height: auto; display: block; }}
  .empty {{ color: #64748B; font-style: italic; }}
  footer {{ margin-top: 28px; color: #64748B; font-size: 11px; }}
</style>
</head>
<body>
<main>
  <h1>{_text(title)}</h1>
  <div class="sub">{subtitle}</div>

  <h2>Asal angka</h2>
  <div class="card">
    <dl class="grid kv">
      {_kv("Snapshot", contract.get("dataset_id"))}
      {_kv("snapshot_id", contract.get("snapshot_id"))}
      {_kv("Kontrak", contract.get("version"))}
      {_kv("Rentang tanggal", _range_text(contract))}
      {_kv("Dibuat", contract.get("snapshot_at"))}
      {_kv("Zona waktu", contract.get("timezone"))}
      {_kv("Mesin", f"{software.get('name', '-')} {software.get('version', '')}".strip())}
    </dl>
  </div>

  <h2>Populasi dan ambang</h2>
  <div class="card">
    <dl class="grid kv">
      {_kv("Artikel", population.get("articles"))}
      {_kv("Entitas", population.get("entities"))}
      {_kv("Penyebutan", population.get("mentions"))}
      {_kv("Penyebutan dibuang", population.get("dropped_mentions"))}
      {_kv("min_support", parameters.get("min_support"))}
      {_kv("min_npmi", parameters.get("min_npmi"))}
      {_kv("Sisi diselamatkan", parameters.get("rescued_edges"))}
      {_kv("Seed", parameters.get("seed"))}
    </dl>
  </div>

  <h2>Angka kunci</h2>
  <div class="card">
    {_summary_table(summary or {})}
  </div>

  <h2>Metode perhitungan</h2>
  <div class="card">
    <div class="sub" style="margin:0 0 8px;">Nama metode, bukan nilainya: ini yang dipakai
      untuk menghasilkan angka di atas, dan yang berubah bila engine berubah.</div>
    {_metrics_table(metrics)}
  </div>

  {_inference_section(inference)}

  <h2>Gambar jaringan</h2>
  <div class="figure">
    {_figure(svg)}
  </div>

  <h2>Catatan analis</h2>
  <div class="card">
    {_annotations_block(annotations or [])}
  </div>

  <h2>{_text(LIMITATIONS_HEADING)}</h2>
  <div class="card">
    {_limitations_block(limitations)}
  </div>

  <footer>
    Laporan ini mandiri: tidak memuat aset eksternal dan tidak memerlukan server.
    Angka di dalamnya hanya berlaku untuk snapshot dan ambang yang tertulis di atas.
  </footer>
</main>
</body>
</html>
"""


def _figure(svg: Optional[str]) -> str:
    """
    Gambar sebagai SVG sebaris, atau keterangan bila tidak ada.

    Dua kegagalan dibedakan: klien tidak mengirim gambar, dan gambar yang
    dikirim ditolak penyaring. Menuliskan keduanya sebagai "tidak diekspor"
    akan menyembunyikan yang kedua.
    """
    if not svg:
        return '<div class="empty">Kanvas tidak ikut diekspor.</div>'
    cleaned = sanitize_svg(svg)
    if not cleaned:
        return '<div class="empty">Gambar ditolak karena tidak lolos penyaringan.</div>'
    return cleaned


def _text(value: Any) -> str:
    """Semua teks lewat sini: satu tempat untuk meng-escape."""
    if value is None or value == "":
        return "&mdash;"
    return html.escape(str(value))


def _kv(label: str, value: Any) -> str:
    return f"<div><dt>{_text(label)}</dt><dd>{_text(value)}</dd></div>"


def _range_text(contract: Dict[str, Any]) -> str:
    span = contract.get("date_range")
    if not isinstance(span, (list, tuple)) or len(span) != 2:
        return "—"
    return f"{span[0]} s.d. {span[1]}"


def _summary_table(summary: Dict[str, Any]) -> str:
    """
    Angka yang biasanya dikutip di luar, dengan nama yang bisa dicocokkan
    kembali ke UI. Nilai kosong tetap kosong; nol adalah hasil ukur.
    """
    communities = summary.get("communities") or {}
    rows = [
        ("Simpul", summary.get("nodes")),
        ("Sisi", summary.get("edges")),
        ("Densitas", summary.get("density")),
        ("Modularitas (Q)", communities.get("modularity")),
        ("Jumlah komunitas", communities.get("count")),
        ("Transitivitas", summary.get("transitivity")),
        ("Diameter", summary.get("diameter")),
        ("Rata-rata panjang lintasan", summary.get("average_path_length")),
        ("Komponen", summary.get("components")),
        ("Simpul terisolasi", summary.get("isolated")),
    ]
    body = "".join(
        f"<tr><td>{_text(label)}</td><td>{_text(_format(value))}</td></tr>"
        for label, value in rows
    )
    return f'<table><thead><tr><th>Ukuran</th><th>Nilai</th></tr></thead><tbody>{body}</tbody></table>'


def _metrics_table(metrics: Dict[str, Any]) -> str:
    if not metrics:
        return '<div class="empty">Metrik belum dihitung untuk snapshot ini.</div>'
    rows = "".join(
        f"<tr><td>{_text(key)}</td><td>{_text(_format(value))}</td></tr>"
        for key, value in metrics.items()
    )
    return f'<table><thead><tr><th>Metrik</th><th>Nilai</th></tr></thead><tbody>{rows}</tbody></table>'


def _inference_section(inference: Dict[str, Any]) -> str:
    null = inference.get("null_model") or {}
    if not null:
        return ""
    resolution = inference.get("p_value_resolution")
    observed = null.get("observed") or {}
    p_value = null.get("p_value") or {}
    z = null.get("z") or {}

    rows = []
    for name in observed:
        test = "tidak teruji" if p_value.get(name) is None else f"p = {_format(p_value[name])}"
        rows.append(
            f"<tr><td>{_text(name)}</td><td>{_text(_format(observed[name]))}</td>"
            f"<td>{_text(_format(z.get(name)))}</td><td>{_text(test)}</td></tr>"
        )
    resolution_text = (
        "Resolusi uji tidak tersedia (tidak ada resample)."
        if resolution is None
        else f"Resolusi uji 1/({null.get('resamples')} + 1) = {_format(resolution)}; "
        "p tidak pernah ditulis 0."
    )
    return f"""
  <h2>Uji statistik</h2>
  <div class="card">
    <div class="sub" style="margin:0 0 8px;">{_text(resolution_text)}</div>
    <table><thead><tr><th>Metrik</th><th>Teramati</th><th>z</th><th>Uji</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table>
  </div>"""


def _annotations_block(annotations: List[Annotation]) -> str:
    if not annotations:
        return '<div class="empty">Belum ada catatan untuk snapshot ini.</div>'
    items = []
    for item in annotations:
        target = (
            "seluruh graf"
            if item.target_type == "graph"
            else f"{item.target_type}: {item.target_id}"
        )
        items.append(
            f'<div class="note"><div>{_text(item.text)}</div>'
            f'<div class="note-meta">{_text(target)} &middot; {_text(item.created_at)}</div></div>'
        )
    return "".join(items)


def _limitations_block(limitations: List[str]) -> str:
    if not limitations:
        return '<div class="empty">Tidak ada catatan batasan yang dilaporkan.</div>'
    items = "".join(f"<li>{_text(item)}</li>" for item in limitations)
    return f"<ul>{items}</ul>"


def _format(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "ya" if value else "tidak"
    if isinstance(value, float):
        # `%.6g` menjaga angka sangat kecil tetap terbaca sebagai 1e-05,
        # bukan dibulatkan menjadi "0" oleh pemangkasan nol di belakang koma.
        return f"{value:.6g}"
    return str(value)

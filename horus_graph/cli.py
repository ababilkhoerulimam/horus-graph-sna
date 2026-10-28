"""CLI horus-graph."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from .contract.validate import validate_bundle
from .io.bundle import load_bundle


def _cmd_validate(args: argparse.Namespace) -> int:
    findings = validate_bundle(Path(args.bundle))
    errors = [f for f in findings if f.level == "error"]
    warns = [f for f in findings if f.level == "warn"]

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2, ensure_ascii=False))
    else:
        print(f"Temuan: {len(errors)} error, {len(warns)} warning")
        for finding in findings:
            print(f"  [{finding.level.upper():5}] {finding.table}:{finding.code} - {finding.message}")
        if not findings:
            print("  Bundle memenuhi kontrak.")
    return 1 if errors else 0


def _cmd_info(args: argparse.Namespace) -> int:
    bundle = load_bundle(Path(args.bundle))
    info = {
        "dataset_id": bundle.manifest.dataset_id,
        "contract_version": bundle.manifest.contract_version,
        "snapshot_at": bundle.manifest.snapshot_at.isoformat(),
        "date_range": [
            str(bundle.manifest.date_range.start),
            str(bundle.manifest.date_range.end),
        ],
        "domain": {
            "id": bundle.domain.domain_id,
            "ego": bundle.domain.ego_id,
            "epochs": [e.id for e in bundle.domain.epochs],
        },
        "counts": bundle.counts(),
        "layers": {
            "transmission": bundle.layer_status("transmission"),
            "sentiment": bundle.layer_status("sentiment"),
        },
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    from .core.anomaly import detect_anomalies
    from .core.backbone import BackboneConfig
    from .core.bipartite import build_bipartite
    from .core.build import backbone_config, build_network
    from .core.temporal import build_temporal

    bundle = load_bundle(Path(args.bundle))
    # Flag eksplisit menang; tanpa flag, ambang milik bundle dipakai. Tanpa
    # urutan ini, `manifest.backbone` tidak akan pernah berpengaruh lewat CLI
    # karena default argparse selalu menimpa nilai dari data.
    base = backbone_config(bundle)
    config = BackboneConfig(
        min_support=args.min_support if args.min_support is not None else base.min_support,
        min_npmi=args.min_npmi if args.min_npmi is not None else base.min_npmi,
        rescue_isolated=base.rescue_isolated,
    )
    network = build_network(bundle, config)

    report: dict = {
        "summary": dict(network.summary),
        "backbone": network.backbone.as_dict(),
        "consensus": network.consensus.as_dict(),
        "provenance": network.provenance(),
    }
    temporal = bipartite = anomaly = None
    if args.all:
        temporal = build_temporal(bundle, BackboneConfig(
            min_support=config.min_support, min_npmi=config.min_npmi, rescue_isolated=False
        ))
        bipartite = build_bipartite(bundle, min_support=config.min_support)
        anomaly = detect_anomalies(bundle)
        report["temporal"] = [
            {
                "id": slice_.window.id,
                "start_year": slice_.window.start_year,
                "end_year": slice_.window.end_year,
                "nodes": slice_.graph.number_of_nodes(),
                "edges": slice_.graph.number_of_edges(),
                "density": slice_.density,
                "articles": slice_.articles,
                "top_broker": slice_.top_broker,
            }
            for slice_ in temporal.slices
        ]
        report["bipartite"] = bipartite.summary()
        report["anomaly"] = {
            "months": anomaly.months,
            "partial_periods": list(anomaly.partial_periods),
            "spikes": [dict(spike) for spike in anomaly.spikes],
        }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0

    summary = network.summary
    print(
        f"Simpul {summary['nodes']} | Edge {summary['edges']} | "
        f"Densitas {summary['density']} | Modularitas {summary['communities']['modularity']}"
    )
    print(
        f"Komunitas {summary['communities']['count']} {summary['communities']['sizes']} | "
        f"Transitivitas {summary['transitivity']} | Diameter {summary['diameter']}"
    )
    backbone = network.backbone
    print(
        f"Backbone: {backbone.candidate_pairs} kandidat, {backbone.above_threshold} lolos ambang, "
        f"{backbone.added_for_support} diselamatkan, {len(backbone.still_isolated)} tetap terisolasi"
    )
    _print_consensus(network.consensus)

    if temporal is not None:
        for slice_ in temporal.slices:
            print(
                f"  {slice_.window.id} {slice_.window.start_year}-{slice_.window.end_year}: "
                f"{slice_.graph.number_of_nodes()} simpul, {slice_.graph.number_of_edges()} edge, "
                f"densitas {slice_.density}, {slice_.articles} artikel"
            )
        assert bipartite is not None and anomaly is not None
        print(
            f"Bipartit: {bipartite.summary()['edges']} edge topik-aktor, "
            f"{bipartite.summary()['actors']} aktor"
        )
        print(
            f"Anomali: {anomaly.months} bulan, {len(anomaly.spikes)} spike, "
            f"bulan parsial {', '.join(anomaly.partial_periods) or '-'}"
        )

    if args.top:
        frame = network.node_metrics.sort_values("betweenness", ascending=False)
        columns = ["degree", "betweenness", "pagerank", "burt_constraint", "louvain_community"]
        print(frame.head(args.top)[columns].to_string())
    return 0


def _print_consensus(consensus) -> None:
    """Stabilitas komunitas: angka yang menjawab 'partisi ini kuat atau tidak'."""
    block = consensus.as_dict()
    if block["status"] != "ready":
        print(f"Stabilitas komunitas: tidak diukur ({block['reason']})")
        return
    print(
        f"Stabilitas komunitas: {block['runs']} jalankan Louvain, "
        f"kesepakatan ARI {block['agreement']}, median {block['stability_median']}, "
        f"{block['unstable_count']} simpul batas"
    )
    for item in block["unstable"]:
        print(f"  batas {item['id']}: {item['stability']}")


def _analysis_context(args: argparse.Namespace):
    """Bundle + jaringan + irisan epos, dipakai bersama perintah analisis."""
    from .core.build import build_network
    from .core.temporal import build_temporal

    bundle = load_bundle(Path(args.bundle))
    network = build_network(bundle)
    temporal = build_temporal(bundle)
    return bundle, network, temporal


def _cmd_inference(args: argparse.Namespace) -> int:
    """
    Hitung null model dan bootstrap di luar server.

    Perintah ini ada karena biayanya puluhan detik: dijalankan sebagai langkah
    build, lalu server hanya membaca artefaknya.
    """
    from .analysis import inference as inference_artifact
    from .core.build import build_network

    bundle = load_bundle(Path(args.bundle))
    network = build_network(bundle)
    params = inference_artifact.InferenceParams(
        resamples=args.resamples,
        bootstrap_resamples=args.bootstrap_resamples,
        seed=args.seed,
        ci=args.ci,
    )
    payload = inference_artifact.compute(bundle, network, params)

    if args.write:
        path = inference_artifact.write_artifact(Path(args.bundle), payload)
        print(f"Artefak ditulis: {path.name}")

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    block = payload["inference"]
    null = block.get("null_model") or {}
    resolution = block.get("p_value_resolution")
    print(
        f"Null model ({null.get('resamples', 0)} resample, seed {null.get('seed')}, "
        f"resolusi p {resolution})"
    )
    for name in ("modularity", "transitivity", "assortativity"):
        observed = (null.get("observed") or {}).get(name)
        p_value = (null.get("p_value") or {}).get(name)
        z = (null.get("z") or {}).get(name)
        if observed is None:
            print(f"  {name:14} tidak terdefinisi")
            continue
        p_text = "tidak teruji" if p_value is None else f"p={p_value}"
        print(f"  {name:14} {observed}  z={z}  {p_text}")

    ari = (block.get("bootstrap") or {}).get("ari") or {}
    if ari.get("mean") is None:
        print("Bootstrap: tidak ada resample")
    else:
        print(
            f"Bootstrap: ARI {ari['mean']} "
            f"(p05 {ari['p05']} - p95 {ari['p95']})"
        )
    return 0


def _cmd_motifs(args: argparse.Namespace) -> int:
    """
    Sensus triad dan rich-club ternormalisasi.

    Dipisahkan dari `build` karena pembanding acak untuk rich-club memakan
    ~1 detik pada 77 simpul dan menit pada graf besar; server tidak pernah
    membayarnya secara interaktif.
    """
    from .analysis import motifs as motif_artifact
    from .core.build import build_network

    bundle = load_bundle(Path(args.bundle))
    network = build_network(bundle)
    params = motif_artifact.MotifParams(
        replicates=args.replicates, swaps_per_edge=args.swaps_per_edge, seed=args.seed
    )
    payload = motif_artifact.compute(network, params)

    if args.write:
        path = motif_artifact.write_artifact(Path(args.bundle), payload)
        print(f"Artefak ditulis: {path.name}")

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    triads = payload["motifs"]["triads"]
    if triads["status"] != "ready":
        print(f"Triad: tidak diukur ({triads['reason']})")
    else:
        share = triads["closed_share"]
        print(
            f"Triad: {triads['triangles']} segitiga, {triads['open_wedges']} baji terbuka, "
            f"{'tidak terdefinisi' if share is None else f'{share * 100:.1f}%'} "
            f"triad bertepi ganda yang tertutup"
        )

    club = payload["motifs"]["rich_club"]
    if club["status"] != "ready":
        print(f"Rich-club: tidak diukur ({club['reason']})")
        return 0
    peak = club.get("peak")
    if peak is None:
        print(f"Rich-club: kurva kosong ({club['replicates']} pembanding)")
    else:
        print(
            f"Rich-club: rasio puncak {peak['ratio']} pada derajat {peak['degree']} "
            f"({club['replicates']} pembanding, seed {params.seed}); "
            "1,0 berarti tidak ada efek di luar derajat"
        )
        if club["truncated_degrees"]:
            print(
                f"  {club['truncated_degrees']} ambang derajat tertinggi tidak dilaporkan: "
                "subgrafnya terlalu kecil untuk memberi rasio yang bisa dipercaya"
            )
    return 0


def _cmd_dossier(args: argparse.Namespace) -> int:
    from .analysis.dossier import entity_dossier

    _, network, temporal = _analysis_context(args)
    print(
        json.dumps(
            entity_dossier(network, args.entity, temporal=temporal),
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    from .analysis.paths import trace_path

    _, network, _ = _analysis_context(args)
    result = trace_path(network, args.origin, args.target)
    if not args.json:
        if not result["success"]:
            print(f"Gagal: {result['message']}")
            return 1
        print(" -> ".join(result["path"]))
        print(
            f"{result['total_hops']} langkah, bobot total {result['total_weight']}, "
            f"NPMI rata-rata {result['average_npmi']}"
        )
        if result["alternative_path"]:
            print("Alternatif: " + " -> ".join(result["alternative_path"]))
        return 0
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cmd_counterfactual(args: argparse.Namespace) -> int:
    from .analysis.counterfactual import simulate_removal

    _, network, _ = _analysis_context(args)
    result = simulate_removal(network, args.entity)
    if not args.json:
        if not result["success"]:
            print(f"Ditolak: {result['message']}")
            return 1
        print(
            f"Hapus {result['removed']['label']}: "
            f"densitas {result['baseline']['density']} -> {result['post']['density']} "
            f"(delta {result['delta_density']}), {result['lost_edges']} edge hilang"
        )
        for item in result["absorbing_brokers"]:
            print(
                f"  penyerap: {item['label']} +{item['delta_betweenness']:.4f} "
                f"({item['pct_shift'] if item['pct_shift'] is not None else '-'}%)"
            )
        return 0
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cmd_briefing(args: argparse.Namespace) -> int:
    from .analysis.briefing import executive_briefing
    from .core.anomaly import detect_anomalies
    from .core.bipartite import build_bipartite

    bundle, network, temporal = _analysis_context(args)
    briefing = executive_briefing(
        network,
        temporal=temporal,
        anomaly=detect_anomalies(bundle),
        bipartite=build_bipartite(bundle),
    )
    if args.json:
        print(json.dumps(briefing, indent=2, ensure_ascii=False))
        return 0

    macro = briefing["macro"]
    print(f"{briefing['dataset']['label']}: {macro['nodes']} simpul, {macro['edges']} edge")
    print(
        f"Densitas {macro['density']} | Modularitas {macro['modularity']} | "
        f"{macro['communities']} komunitas {macro['community_sizes']}"
    )
    broker = briefing["critical_broker"]
    if broker:
        print(f"Broker kritis: {broker['label']} (betweenness {broker['betweenness']})")
    for spike in briefing["anomaly"]["spikes"]:
        print(
            f"  lonjakan {spike['period']}: {spike['article_count']} artikel "
            f"(z {spike['z_score']}, {spike['severity']})"
        )
    print(f"Lapisan: transmission={briefing['layers']['transmission']}, sentiment={briefing['layers']['sentiment']}")
    return 0


def _cmd_enhance(args: argparse.Namespace) -> int:
    from .enhance import (
        bootstrap_network,
        degree_preserving_null,
        detect_bursts,
        epoch_turnover,
        reporting_block,
        topology_profile,
        turnover_summary,
    )

    bundle, network, temporal = _analysis_context(args)
    null = (
        None
        if args.no_null
        else degree_preserving_null(network, resamples=args.resamples, seed=args.seed)
    )
    bootstrap = (
        None
        if args.no_bootstrap
        else bootstrap_network(
            network, resamples=args.bootstrap_resamples, seed=args.seed, ci=args.ci
        )
    )
    topology = topology_profile(network)
    turnover = epoch_turnover(temporal)
    bursts = detect_bursts(bundle)

    block = reporting_block(
        bundle, network, null=null, bootstrap=bootstrap, topology=topology, seed=args.seed
    )
    block["turnover"] = {
        "transitions": list(turnover.to_dict(orient="records")),
        "summary": turnover_summary(temporal),
    }
    block["bursts"] = {
        "count": 0 if bursts.bursts.empty else len(bursts.bursts),
        "top": [] if bursts.bursts.empty else bursts.bursts.head(args.top).to_dict(orient="records"),
        "method": "kleinberg_two_state_viterbi",
    }

    if args.json:
        print(json.dumps(block, indent=2, ensure_ascii=False, default=str))
        return 0

    _print_enhance(block, topology, args.top)
    return 0


def _print_enhance(block: dict, topology, top: int) -> None:
    if "inference" in block:
        null = block["inference"]["null_model"]
        print("Null model (derajat terjaga):")
        for name, observed in null["observed"].items():
            print(
                f"  {name:14} {observed} vs acak {null['null_mean'][name]} "
                f"(z {null['z'][name]}, p {null['p_value'][name]})"
            )
        print(f"  resolusi p 1/{null['resamples'] + 1}")
        boot = block["inference"].get("bootstrap")
        if boot:
            print(f"Bootstrap artikel: ARI {boot['ari']['mean']} "
                  f"[{boot['ari']['p05']}, {boot['ari']['p95']}], {boot['resamples']} resample")

    print(
        f"Topologi: k-core maks {topology.max_core} "
        f"({len(topology.core_nodes)} inti, {len(topology.periphery_nodes)} pinggiran) | "
        f"asortativitas derajat {topology.degree_assortativity} | tipe {topology.type_assortativity}"
    )

    turnover = block["turnover"]["summary"]
    print(
        f"Perputaran: {turnover['transitions']} transisi, "
        f"Jaccard tepi rata-rata {turnover['mean_edge_jaccard']}"
    )
    for row in block["turnover"]["transitions"]:
        print(
            f"  {row['from_epoch']} -> {row['to_epoch']}: "
            f"+{row['edges_added']} -{row['edges_removed']} edge, "
            f"Jaccard {row['edge_jaccard']}"
        )

    print(f"Burst: {block['bursts']['count']} rentang")
    for row in block["bursts"]["top"]:
        print(
            f"  {row['entity_id']} {row['start']}..{row['end']} "
            f"lift {row['lift']} ({row['articles']} artikel)"
        )

    print("Batasan:")
    for note in block["limitations"]:
        print(f"  - {note}")


def _cmd_serve(args: argparse.Namespace) -> int:
    from .api.app import run
    from .env import load_env_file

    # Dimuat sebelum server berjalan; variabel yang sudah ada di shell menang.
    load_env_file()
    run(
        bundle=args.bundle,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from .api.state import get_state
    from .export import formats

    state = get_state(args.bundle)
    body = formats.render(state.network, args.format)

    if args.out == "-":
        sys.stdout.write(body)
        return 0

    Path(args.out).write_text(body, encoding="utf-8")
    print(f"Ditulis: {args.out} ({len(body)} bita)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="horus-graph", description="SNA engine")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validasi bundle terhadap kontrak")
    validate.add_argument("bundle")
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(func=_cmd_validate)

    info = sub.add_parser("info", help="Ringkasan isi bundle")
    info.add_argument("bundle")
    info.set_defaults(func=_cmd_info)

    build = sub.add_parser("build", help="Bangun jaringan co-occurrence dan hitung metrik")
    build.add_argument("bundle")
    build.add_argument("--min-support", type=int, default=None,
                       help="Default: ambang milik bundle (manifest.backbone), lalu 3")
    build.add_argument("--min-npmi", type=float, default=None,
                       help="Default: ambang milik bundle (manifest.backbone), lalu 0.2")
    build.add_argument("--top", type=int, default=0, help="Tampilkan N simpul betweenness tertinggi")
    build.add_argument("--all", action="store_true", help="Ikut hitung temporal, bipartit, anomali")
    build.add_argument("--json", action="store_true")
    build.set_defaults(func=_cmd_build)

    inference = sub.add_parser(
        "inference", help="Hitung null model dan bootstrap (mahal; simpan sebagai artefak)"
    )
    inference.add_argument("bundle")
    inference.add_argument("--resamples", type=int, default=200)
    inference.add_argument("--bootstrap-resamples", type=int, default=200)
    inference.add_argument("--seed", type=int, default=42)
    inference.add_argument("--ci", type=float, default=90.0, help="Lebar selang kepercayaan")
    inference.add_argument("--write", action="store_true",
                           help="Simpan hasil ke <bundle>/inference.json agar dibaca server")
    inference.add_argument("--json", action="store_true")
    inference.set_defaults(func=_cmd_inference)

    motifs_parser = sub.add_parser(
        "motifs", help="Sensus triad dan rich-club ternormalisasi (mahal; simpan sebagai artefak)"
    )
    motifs_parser.add_argument("bundle")
    motifs_parser.add_argument(
        "--replicates", type=int, default=10, help="Jumlah graf acak pembanding untuk rich-club"
    )
    motifs_parser.add_argument(
        "--swaps-per-edge",
        type=int,
        default=10,
        dest="swaps_per_edge",
        help="Pertukaran sisi per sisi pada tiap graf acak",
    )
    motifs_parser.add_argument("--seed", type=int, default=42)
    motifs_parser.add_argument(
        "--write", action="store_true", help="Simpan hasil ke <bundle>/motifs.json"
    )
    motifs_parser.add_argument("--json", action="store_true")
    motifs_parser.set_defaults(func=_cmd_motifs)

    dossier = sub.add_parser("dossier", help="Profil satu entitas")
    dossier.add_argument("bundle")
    dossier.add_argument("entity")
    dossier.set_defaults(func=_cmd_dossier)

    path = sub.add_parser("path", help="Rute terkuat antara dua entitas")
    path.add_argument("bundle")
    path.add_argument("origin")
    path.add_argument("target")
    path.add_argument("--json", action="store_true")
    path.set_defaults(func=_cmd_path)

    counterfactual = sub.add_parser(
        "counterfactual", help="Simulasi penghapusan satu simpul"
    )
    counterfactual.add_argument("bundle")
    counterfactual.add_argument("entity")
    counterfactual.add_argument("--json", action="store_true")
    counterfactual.set_defaults(func=_cmd_counterfactual)

    briefing = sub.add_parser("briefing", help="Ringkasan eksekutif")
    briefing.add_argument("bundle")
    briefing.add_argument("--json", action="store_true")
    briefing.set_defaults(func=_cmd_briefing)

    enhance = sub.add_parser(
        "enhance", help="Uji null, bootstrap, topologi, perputaran, burst, dan batasan"
    )
    enhance.add_argument("bundle")
    enhance.add_argument("--resamples", type=int, default=200, help="Resample null model")
    enhance.add_argument("--bootstrap-resamples", type=int, default=200)
    enhance.add_argument("--ci", type=float, default=90.0, help="Lebar selang bootstrap (%)")
    enhance.add_argument("--seed", type=int, default=42)
    enhance.add_argument("--top", type=int, default=5)
    enhance.add_argument("--no-null", action="store_true", help="Lewati null model")
    enhance.add_argument("--no-bootstrap", action="store_true", help="Lewati bootstrap")
    enhance.add_argument("--json", action="store_true")
    enhance.set_defaults(func=_cmd_enhance)

    serve = sub.add_parser("serve", help="Jalankan API + visualizer")
    serve.add_argument(
        "--bundle", default=None, help="Path bundle (default: HORUS_BUNDLE atau data/bundles/)"
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=_cmd_serve)

    export_graph = sub.add_parser(
        "export", help="Ekspor jaringan ke GraphML, GEXF, atau CSV"
    )
    export_graph.add_argument("bundle", help="Direktori bundle")
    export_graph.add_argument(
        "--format",
        choices=["graphml", "gexf", "csv"],
        default="graphml",
        help="graphml/gexf memuat metrik simpul; csv berisi daftar sisi",
    )
    export_graph.add_argument(
        "--out", default="-", help="Berkas tujuan; '-' menulis ke stdout"
    )
    export_graph.set_defaults(func=_cmd_export)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI harus memberi pesan, bukan traceback
        print(f"GAGAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

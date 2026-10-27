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


def _cmd_export_legacy(args: argparse.Namespace) -> int:
    from .export.legacy import export_legacy_bundle

    result = export_legacy_bundle(
        repo=Path(args.repo),
        out=Path(args.out),
        limit=args.limit,
        progress=args.progress,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
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

    export = sub.add_parser(
        "export-legacy", help="(migrasi) ekspor korpus horus-agent menjadi bundle"
    )
    export.add_argument("--repo", required=True, help="Path repo horus-agent")
    export.add_argument("--out", required=True, help="Direktori bundle tujuan")
    export.add_argument("--limit", type=int, default=None, help="Batasi jumlah artikel")
    export.add_argument("--progress", action="store_true")
    export.set_defaults(func=_cmd_export_legacy)

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

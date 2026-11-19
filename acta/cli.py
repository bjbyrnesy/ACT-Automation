from __future__ import annotations

import argparse
import sys
from pathlib import Path

from acta.create import run_create
from acta.extend import extend_topology


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acta.py",
        description=(
            "ACT Automation — create, extend, upload, and onboard fabric labs "
            "(ACT + containerlab). Capacity reserved at create time; extend only "
            "uses unused ports (existing endpoints stay fixed)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "create",
        help=(
            "Interactive ACT topology create (pinned serials/MACs, "
            "spare spine/leaf/mleaf capacity)"
        ),
    )
    extend = sub.add_parser(
        "extend",
        help="Grow an existing topology on unused ports",
        description=(
            "Grow an existing topology using unused ports only. Existing "
            "node:Ethernet endpoints never change."
        ),
    )
    extend.add_argument(
        "topology",
        type=Path,
        help="ACT topology YAML (default: overwrite in place)",
    )
    extend.add_argument(
        "--add",
        choices=("spine", "leaf", "pair", "mleaf"),
        required=True,
        help="What to add",
    )
    extend.add_argument(
        "--site",
        help=(
            "Site letter (A-D); required for multi-DC topologies, "
            "scopes the extension to that site"
        ),
    )
    extend.add_argument(
        "--pair",
        type=int,
        help=(
            "1-based index over discovered MLAG peer-linked leaf pairs, "
            "sorted by lowest leaf index"
        ),
    )
    extend.add_argument(
        "--count",
        type=int,
        default=1,
        help="How many leaves or member leaves to add (default: 1)",
    )
    output = extend.add_mutually_exclusive_group()
    output.add_argument(
        "--out",
        type=Path,
        help="Write result to PATH; leave input unchanged",
    )
    output.add_argument(
        "--new",
        action="store_true",
        help="Write a new dated topology file beside the input",
    )
    sub.add_parser(
        "upload",
        help="Upload topology YAML to ACT; optional lab create/deploy",
    )
    sub.add_parser(
        "onboard",
        help="Onboard a Running ACT lab to CVaaS (TerminAttr over SSH)",
    )
    clab = sub.add_parser(
        "clab",
        help="Containerlab: generate, deploy, onboard cEOS labs",
    )
    clab_sub = clab.add_subparsers(dest="clab_command", required=True)
    clab_sub.add_parser("generate", help="Convert ACT topology YAML to containerlab")
    clab_sub.add_parser("deploy", help="Deploy a .clab.yml locally or via --host")
    clab_sub.add_parser("onboard", help="Onboard cEOS containers to CVaaS")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "create":
        try:
            run_create(Path.cwd())
        except (EOFError, RuntimeError, ValueError) as error:
            print(f"ERROR: {error}", file=sys.stderr, flush=True)
            return 2
        return 0
    if args.command == "extend":
        try:
            output_path = extend_topology(
                args.topology,
                args.add,
                site=args.site,
                pair=args.pair,
                count=args.count,
                out=args.out,
                new=args.new,
            )
        except (NotImplementedError, OSError, RuntimeError, ValueError) as error:
            print(f"ERROR: {error}", file=sys.stderr, flush=True)
            return 2
        print(f"Wrote {output_path}")
        return 0
    print(f"ERROR: command {args.command!r} not implemented yet", flush=True)
    return 2

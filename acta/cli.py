from __future__ import annotations

import argparse
import sys
from pathlib import Path

from acta.create import run_create
from acta.extend import ExtendResult, extend_topology, topology_sites
from acta.prompt import prompt_value

_ADD_CHOICES = ("spine", "leaf", "pair", "mleaf")


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
        choices=_ADD_CHOICES,
        help="What to add (prompted when omitted in an interactive terminal)",
    )
    extend.add_argument(
        "--site",
        help=(
            "Site letter (A-D); required for multi-DC topologies "
            "(prompted when omitted in an interactive terminal)"
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


def _prompt_choice(label: str, choices: tuple[str, ...] | list[str]) -> str:
    """Prompt until the answer is one of ``choices`` (case-insensitive)."""
    options = "/".join(choices)
    while True:
        answer = prompt_value(f"{label} ({options})").strip().casefold()
        for choice in choices:
            if answer == choice.casefold():
                return choice
        print(f"  Enter one of: {options}.", file=sys.stderr)


def _prompt_pair() -> int:
    while True:
        answer = prompt_value("Leaf pair number (1 = lowest-numbered pair)").strip()
        if answer.isdecimal() and int(answer) >= 1:
            return int(answer)
        print("  Enter a whole number of at least 1.", file=sys.stderr)


def _print_extend_result(result: ExtendResult) -> None:
    print(f"Wrote {result.path}")
    print(f"Added: {', '.join(result.added_nodes)}")
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    print(result.free_slots_summary())


def _run_extend(args: argparse.Namespace) -> int:
    interactive = sys.stdin.isatty()
    add: str | None = args.add
    if add is None:
        if not interactive:
            print(
                f"ERROR: --add is required ({', '.join(_ADD_CHOICES)})",
                file=sys.stderr,
                flush=True,
            )
            return 2
        add = _prompt_choice("What to add", _ADD_CHOICES)
    site: str | None = args.site
    pair: int | None = args.pair
    if interactive and site is None:
        sites = topology_sites(args.topology)
        if sites:
            site = _prompt_choice("Site", sites)
    if interactive and add == "mleaf" and pair is None:
        pair = _prompt_pair()
    result = extend_topology(
        args.topology,
        add,
        site=site,
        pair=pair,
        count=args.count,
        out=args.out,
        new=args.new,
    )
    _print_extend_result(result)
    return 0


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
            return _run_extend(args)
        except (
            EOFError,
            NotImplementedError,
            OSError,
            RuntimeError,
            ValueError,
        ) as error:
            print(f"ERROR: {error}", file=sys.stderr, flush=True)
            return 2
    print(f"ERROR: command {args.command!r} not implemented yet", flush=True)
    return 2

from __future__ import annotations

import argparse


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
    sub.add_parser("extend", help="Grow an existing topology on unused ports")
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
    print(f"ERROR: command {args.command!r} not implemented yet", flush=True)
    return 2

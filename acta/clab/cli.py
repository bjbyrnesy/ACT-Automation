"""Argument parser for the legacy containerlab entry point."""

import argparse
import sys
from pathlib import Path

from .deploy import deploy, redeploy
from .destroy import destroy
from .generate import generate
from .onboard import onboard
from .support import config_flag, config_image, config_ip_list, read_config


def main(argv=None):
    config = read_config()
    parser = argparse.ArgumentParser(
        prog="acta.py clab",
        description=(
            "Generate, deploy, destroy, redeploy, and onboard containerlab labs "
            "derived from ACT topologies."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser(
        "generate",
        help="Convert an acta.py act create ACT topology to containerlab YAML",
    )
    gen.add_argument("source")
    gen.add_argument(
        "--name",
        default=None,
        help=(
            "Lab name (default: hostname prefix from the ACT topology, else "
            "CLAB_NAME / filename)"
        ),
    )
    gen.add_argument(
        "--image",
        default=config_image(config),
        help="cEOS image (default: CLAB_IMAGE or ceos:$EOS_VERSION from .config)",
    )
    gen.add_argument("--output")
    gen.add_argument(
        "--mgmt-subnet",
        default=config.get("CLAB_MGMT_SUBNET") or "172.100.100.0/22",
        help="IPv4 management subnet (default: CLAB_MGMT_SUBNET or 172.100.100.0/22)",
    )
    gen.add_argument(
        "--mgmt-gateway",
        default=config.get("CLAB_MGMT_GATEWAY") or None,
        help="Management IPv4 gateway",
    )
    gen.add_argument(
        "--mgmt-range",
        default=config.get("CLAB_MGMT_RANGE") or None,
        help="Management IPv4 allocation range in CIDR notation",
    )
    gen.add_argument(
        "--mgmt-bridge",
        default=config.get("CLAB_MGMT_BRIDGE") or None,
        help=(
            "Linux bridge interface name for mgmt (containerlab mgmt.bridge; "
            "≤15 chars). Not the Docker/Podman network name — use --mgmt-network. "
            "Only applied when the network is created; destroy an existing "
            "mgmt network first if changing the bridge."
        ),
    )
    gen.add_argument(
        "--mgmt-mtu",
        type=int,
        default=config.get("CLAB_MGMT_MTU") or None,
        help="Management network MTU",
    )
    gen.add_argument(
        "--mgmt-network",
        default=config.get("CLAB_MGMT_NETWORK") or None,
        help="Management network name (default: CLAB_MGMT_NETWORK or clab)",
    )
    gen.add_argument(
        "--name-servers",
        nargs="+",
        default=config_ip_list(config, "CLAB_DNS", ["8.8.8.8", "1.1.1.1"]),
        metavar="IP",
        help="IPv4 name servers for MGMT (default: CLAB_DNS from .config, else 8.8.8.8 1.1.1.1)",
    )
    gen.add_argument(
        "--ntp-servers",
        nargs="*",
        default=config_ip_list(config, "CLAB_NTP"),
        metavar="IP",
        help="IPv4 NTP servers for MGMT (default: CLAB_NTP from .config)",
    )
    gen.set_defaults(func=generate)
    from_act_default = config_flag(config.get("CLAB_FROM_ACT"), default=False)
    for command, handler in (
        ("deploy", deploy),
        ("destroy", destroy),
        ("redeploy", redeploy),
        ("onboard", onboard),
    ):
        action = sub.add_parser(command)
        action.add_argument(
            "topology",
            help=(
                "Project .clab.yml, or an ACT topology when --from-act / "
                "CLAB_FROM_ACT=y is set"
            ),
        )
        action.add_argument(
            "--host",
            default=config.get("CLAB_HOST") or None,
            help="SSH alias or user@host (default: CLAB_HOST from .config; omit to run locally)",
        )
        runtime_default = (
            "podman" if command in {"deploy", "destroy", "redeploy"} else None
        )
        action.add_argument(
            "--runtime",
            choices=("docker", "podman"),
            default=runtime_default,
            help=(
                "Container runtime (deploy/destroy/redeploy default to podman; "
                "onboarding auto-detects)"
            ),
        )
        action.add_argument(
            "--from-act",
            dest="from_act",
            action="store_true",
            default=from_act_default,
            help=(
                "Accept an acta.py act create topology and generate .clab.yml first "
                "(default: CLAB_FROM_ACT from .config)"
            ),
        )
        action.add_argument(
            "--no-from-act",
            dest="from_act",
            action="store_false",
            help="Require a project-generated .clab.yml (ignore CLAB_FROM_ACT)",
        )
        action.add_argument(
            "--name",
            default=config.get("CLAB_NAME") or None,
            help="Lab name when converting from ACT (default: CLAB_NAME or topology stem)",
        )
        action.add_argument(
            "--image",
            default=config_image(config),
            help="cEOS image when converting from ACT (default: CLAB_IMAGE / EOS_VERSION)",
        )
        if command in {"deploy", "redeploy"}:
            action.add_argument(
                "--mgmt-network",
                default=config.get("CLAB_MGMT_NETWORK") or None,
                help=(
                    "Docker/Podman management network name for this deployment "
                    "(default: CLAB_MGMT_NETWORK). Distinct from --mgmt-bridge."
                ),
            )
            action.add_argument(
                "--mgmt-bridge",
                default=config.get("CLAB_MGMT_BRIDGE") or None,
                help=(
                    "Linux bridge interface name for this deployment "
                    "(default: CLAB_MGMT_BRIDGE). Only takes effect when the "
                    "mgmt network is created; destroy the existing network first "
                    "if changing the bridge on Docker."
                ),
            )
        if command == "onboard":
            action.add_argument(
                "--endpoint",
                default=config.get("CVAAS_HOST") or None,
                help="CVaaS hostname (default: CVAAS_HOST from .config, else prompt)",
            )
            disableaaa_default = config_flag(
                config.get("CLAB_DISABLEAAA"), default=False
            )
            action.add_argument(
                "--disableaaa",
                dest="disableaaa",
                action="store_true",
                default=disableaaa_default,
                help="Pass -disableaaa to TerminAttr (default: CLAB_DISABLEAAA from .config)",
            )
            action.add_argument(
                "--no-disableaaa",
                dest="disableaaa",
                action="store_false",
                help="Do not pass -disableaaa to TerminAttr",
            )
        action.set_defaults(func=handler)

    show = sub.add_parser(
        "show",
        help="Show fabric summary / SSH reachability for a local or remote lab",
    )
    show.add_argument(
        "topology",
        type=Path,
        help="ACT topology YAML or .clab.yml",
    )
    show_view = show.add_mutually_exclusive_group()
    show_view.add_argument(
        "--image",
        action="store_true",
        help="Force Kitty-graphics inline PNG even if auto-detect is unsure",
    )
    show_view.add_argument(
        "--plain",
        action="store_true",
        help="Skip inline image (tables + PNG path only; default when not a TTY)",
    )
    show.add_argument(
        "--no-ssh",
        action="store_true",
        help="Skip SSH reachability probes of management IPs",
    )
    show.add_argument(
        "--host",
        default=config.get("CLAB_HOST") or None,
        help="SSH alias or user@host (default: CLAB_HOST from .config)",
    )
    show.add_argument(
        "--runtime",
        choices=("docker", "podman"),
        default=None,
        help="Container runtime of the remote lab (informational)",
    )

    def _run_show(show_args):
        from acta.show_topo import run_show

        return run_show(
            show_args.topology,
            plain=show_args.plain,
            force_image=show_args.image,
            skip_probe=show_args.no_ssh,
            host=show_args.host,
            runtime=show_args.runtime,
        )

    show.set_defaults(func=_run_show)

    args = parser.parse_args(argv)
    args.config = config
    try:
        result = args.func(args)
        if isinstance(result, int):
            return result
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0

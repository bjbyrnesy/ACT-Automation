"""Argument parser for the legacy containerlab entry point."""

import argparse
import sys

from .deploy import deploy
from .generate import generate
from .onboard import onboard
from .support import config_flag, config_image, config_ip_list, read_config


def main(argv=None):
    config = read_config()
    parser = argparse.ArgumentParser(
        description="Generate, deploy and onboard containerlab labs derived from ACT topologies."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser(
        "generate", help="Convert a generate.sh ACT topology to containerlab YAML"
    )
    gen.add_argument("source")
    gen.add_argument(
        "--name",
        default=config.get("CLAB_NAME") or None,
        help="Lab name (default: CLAB_NAME from .config)",
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
        help="Host management bridge name",
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
    for command, handler in [("deploy", deploy), ("onboard", onboard)]:
        action = sub.add_parser(command)
        action.add_argument("topology")
        action.add_argument(
            "--host",
            default=config.get("CLAB_HOST") or None,
            help="SSH alias or user@host (default: CLAB_HOST from .config; omit to run locally)",
        )
        action.add_argument(
            "--runtime",
            choices=("docker", "podman"),
            default="docker" if command == "deploy" else None,
            help="Container runtime (deploy defaults to docker; onboarding auto-detects)",
        )
        if command == "deploy":
            action.add_argument(
                "--mgmt-network",
                default=config.get("CLAB_MGMT_NETWORK") or None,
                help="Management network for this deployment (default: CLAB_MGMT_NETWORK)",
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
    args = parser.parse_args(argv)
    args.config = config
    try:
        args.func(args)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0

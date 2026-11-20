from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from acta.act_api import ActClient
from acta.clab.support import validate_enrollment_token
from acta.config import load_config, save_config
from acta.create import run_create
from acta.extend import ExtendResult, extend_topology, topology_sites
from acta.onboard_act import CVAAS_PORT_DEFAULT, run_onboard_act
from acta.prompt import prompt_value
from acta.upload import DEFAULT_ACT_TENANT, run_upload

_ADD_CHOICES = ("spine", "leaf", "pair", "mleaf")
_CVAAS_HOST_PROD = "apiserver.arista.io"
_CVAAS_HOST_STAGING = "apiserver.cv-staging.corp.arista.io"
_PROJECT_DIR = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acta.py",
        description=(
            "ACT Automation — acta.py act … / clab … plus show, attach, and ssh. "
            "Capacity reserved at create time; extend only uses unused ports "
            "(existing endpoints stay fixed). Attach hosts after the fabric exists."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    act = sub.add_parser(
        "act",
        help="ACT: create, extend, upload, onboard vEOS labs",
    )
    act_sub = act.add_subparsers(dest="act_command", required=True)

    create = act_sub.add_parser(
        "create",
        help=(
            "Interactive topology create (pinned serials/MACs, "
            "spare spine/leaf/mleaf capacity)"
        ),
    )
    create.add_argument(
        "--for",
        dest="create_for",
        choices=("act", "clab", "both"),
        default=None,
        help=(
            "What to emit: ACT YAML, containerlab lab, or both "
            "(default: CREATE_FOR from .config, else act)"
        ),
    )
    create.add_argument(
        "--name",
        help="containerlab lab name when --for clab/both (default: CLAB_NAME)",
    )
    create.add_argument(
        "--image",
        help="cEOS image when --for clab/both (default: CLAB_IMAGE / EOS_VERSION)",
    )

    extend = act_sub.add_parser(
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

    upload = act_sub.add_parser(
        "upload",
        help="Upload topology YAML to ACT; optional lab create/deploy",
    )
    upload.add_argument(
        "topology",
        type=Path,
        help="ACT topology YAML to upload",
    )
    deploy = upload.add_mutually_exclusive_group()
    deploy.add_argument(
        "--deploy",
        action="store_true",
        default=None,
        help="Create and deploy a lab after upload (skip prompt)",
    )
    deploy.add_argument(
        "--no-deploy",
        action="store_true",
        help="Upload only; do not create/deploy a lab (skip prompt)",
    )
    upload.add_argument(
        "--tenant",
        help="ACT tenant (default: ACT_TENANT / prompt)",
    )

    act_sub.add_parser(
        "onboard",
        help="Onboard a Running ACT lab to CVaaS (TerminAttr over SSH)",
        description=(
            "List Running ACT labs, pick one, and paste TerminAttr "
            "onboarding over SSH to vEOS devices for CVaaS."
        ),
    )

    clab = sub.add_parser(
        "clab",
        help="Containerlab: create, generate, deploy, onboard cEOS labs",
    )
    clab_sub = clab.add_subparsers(dest="clab_command", required=True)
    clab_sub.add_parser(
        "create",
        help="Interactive fabric create for containerlab (default --for clab)",
    )
    clab_sub.add_parser("generate", help="Convert ACT topology YAML to containerlab")
    clab_sub.add_parser("deploy", help="Deploy a .clab.yml locally or via --host")
    clab_sub.add_parser("onboard", help="Onboard cEOS containers to CVaaS")

    show = sub.add_parser(
        "show",
        help="Show fabric summary, MLAG pairs, and Graphviz PNG (inline when supported)",
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
        default=None,
        help=(
            "SSH alias or user@host for a remote clab lab "
            "(probe TCP/22 and containerlab inspect on that host; "
            "default: CLAB_HOST from .config when set)"
        ),
    )
    show.add_argument(
        "--runtime",
        choices=("podman", "docker"),
        default=None,
        help="Container runtime of the remote lab (informational; default: podman)",
    )

    ssh = sub.add_parser(
        "ssh",
        help="Shell into a running lab node (podman/docker exec; host or switch)",
    )
    ssh.add_argument(
        "node",
        help="Container/node name or unique fragment (e.g. blz2-host1, A-leaf1, host1)",
    )
    ssh.add_argument(
        "--runtime",
        choices=("podman", "docker"),
        default=None,
        help="Container runtime (default: podman if available, else docker)",
    )
    ssh.add_argument(
        "remote_command",
        nargs="*",
        default=[],
        help="Optional command (use -- before flags that look like options)",
    )

    attach = sub.add_parser(
        "attach",
        help="Attach a host (generic/linux) to a named switch after the fabric exists",
    )
    attach.add_argument(
        "object_type",
        choices=("host",),
        help="Object to attach (v1: host)",
    )
    attach.add_argument("name", help="Host hostname (same in ACT and clab)")
    attach.add_argument("topology", type=Path, help="ACT topology YAML or .clab.yml")
    attach.add_argument(
        "--to",
        action="append",
        default=[],
        metavar="SWITCH[:EthernetN]",
        help="Switch endpoint (repeat twice for dual-homed). Port optional.",
    )
    attach.add_argument(
        "--mlag-pair",
        type=int,
        help="1-based MLAG leaf pair index from acta.py show",
    )
    attach.add_argument(
        "--mleaf",
        type=int,
        help="1-based member-leaf index from acta.py show",
    )
    attach.add_argument(
        "--et",
        type=int,
        help="Ethernet port on the switch (MLAG peers or --mleaf target)",
    )
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


def _deploy_flag(args: argparse.Namespace) -> bool | None:
    if args.deploy:
        return True
    if args.no_deploy:
        return False
    return None


def _run_upload(args: argparse.Namespace) -> int:
    run_upload(
        args.topology,
        deploy=_deploy_flag(args),
        tenant=args.tenant,
        project_dir=_PROJECT_DIR,
    )
    return 0


def _prompt_cvaas_host(cached: str) -> str:
    host = cached.strip()
    if host:
        print(f"CVaaS environment: {host} (cached)")
        change = prompt_value("Change it? [y/N]", default="n").strip().casefold()
        if change not in {"y", "yes"}:
            return host
        host = ""
    print("CVaaS environment:")
    print(f"  1) Production  ({_CVAAS_HOST_PROD})")
    print(f"  2) Staging     ({_CVAAS_HOST_STAGING})")
    print("  3) Custom URL")
    while True:
        choice = prompt_value("Select CVaaS environment [1-3]").strip()
        if choice == "1":
            return _CVAAS_HOST_PROD
        if choice == "2":
            return _CVAAS_HOST_STAGING
        if choice == "3":
            custom = prompt_value("Enter CVaaS host").strip()
            if custom:
                return custom
            print("  Host cannot be blank.", file=sys.stderr)
            continue
        print("  Invalid choice.", file=sys.stderr)


def _choose_lab(labs: list[dict[str, Any]]) -> dict[str, Any]:
    print("Running labs:")
    for index, lab in enumerate(labs, start=1):
        name = lab.get("name") or lab.get("id")
        print(f"  {index}) {name} ({lab.get('id')})")
    while True:
        answer = prompt_value("Select lab number").strip()
        if answer.isdecimal():
            index = int(answer)
            if 1 <= index <= len(labs):
                return labs[index - 1]
        print(f"  Enter a number from 1 to {len(labs)}.", file=sys.stderr)


def _run_ssh_eos(host: str, commands: str, username: str, password: str) -> None:
    """Paste EOS CLI commands over SSH (``onboard.sh`` ``ssh_eos`` parity)."""
    ssh = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "ConnectTimeout=10",
        f"{username}@{host}",
    ]
    if shutil.which("sshpass"):
        completed = subprocess.run(
            ["sshpass", "-p", password, *ssh],
            input=commands,
            text=True,
            check=False,
            capture_output=True,
        )
    else:
        with tempfile.NamedTemporaryFile(
            "w",
            prefix="acta-askpass-",
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write("#!/bin/sh\n")
            handle.write(f"printf '%s\\n' {shlex.quote(password)}\n")
            askpass = Path(handle.name)
        try:
            askpass.chmod(0o700)
            env = os.environ.copy()
            env["SSH_ASKPASS"] = str(askpass)
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env.setdefault("DISPLAY", "dummy:0")
            completed = subprocess.run(
                ssh,
                input=commands,
                text=True,
                check=False,
                capture_output=True,
                env=env,
            )
        finally:
            askpass.unlink(missing_ok=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"SSH onboard to {host} failed"
            + (f": {detail}" if detail else f" (exit {completed.returncode})")
        )


def _run_onboard() -> int:
    config_path = _PROJECT_DIR / ".config"
    config = load_config(config_path)

    print("ACT API access:")
    act_tenant = prompt_value(
        "ACT tenant",
        os.environ.get("ACT_TENANT") or config.get("ACT_TENANT") or DEFAULT_ACT_TENANT,
    )
    act_user = prompt_value(
        "ACT username (e.g. firstname.lastname)",
        os.environ.get("ACT_USER") or config.get("ACT_USER") or "",
    )
    api_key = os.environ.get("ACT_API_KEY") or config.get("ACT_API_KEY")
    if not api_key:
        api_key = prompt_value("ACT API key", secret=True)

    print("\nCVaaS onboarding:")
    cvaas_host = _prompt_cvaas_host(
        os.environ.get("CVAAS_HOST") or config.get("CVAAS_HOST") or ""
    )
    print(f"Using CVaaS host: {cvaas_host}")
    cvaas_token = os.environ.get("CVAAS_TOKEN") or config.get("CVAAS_TOKEN") or ""
    if cvaas_token:
        try:
            validate_enrollment_token(cvaas_token)
        except ValueError:
            print(
                "Cached CVaaS enrollment token is expired or invalid; "
                "enter a new token."
            )
            cvaas_token = ""
    if not cvaas_token:
        cvaas_token = prompt_value("CVaaS enrollment token", secret=True)
    validate_enrollment_token(cvaas_token)
    cvaas_user = prompt_value(
        "Your CVaaS username",
        os.environ.get("CVAAS_USER") or config.get("CVAAS_USER") or "",
    )
    for label, value in (
        ("ACT_TENANT", act_tenant),
        ("ACT_USER", act_user),
        ("ACT_API_KEY", api_key),
        ("CVAAS_TOKEN", cvaas_token),
        ("CVAAS_USER", cvaas_user),
    ):
        if not value:
            raise ValueError(f"{label} is required and cannot be blank")

    config.update(
        {
            "ACT_TENANT": act_tenant,
            "ACT_USER": act_user,
            "ACT_API_KEY": api_key,
            "CVAAS_HOST": cvaas_host,
            "CVAAS_TOKEN": cvaas_token,
            "CVAAS_USER": cvaas_user,
        }
    )
    save_config(config_path, config)

    client = ActClient(f"https://{act_tenant}.act.arista.com/rest/v1", api_key)
    print(f"\nLogging into ACT ({act_tenant})...")
    client.login()
    run_onboard_act(
        client,
        act_user=act_user,
        cvaas_token=cvaas_token,
        cvaas_host=cvaas_host,
        cvaas_port=CVAAS_PORT_DEFAULT,
        run_ssh=_run_ssh_eos,
        choose_lab=_choose_lab,
    )
    print("Done. TerminAttr onboarding commands pasted to Running lab devices.")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "clab":
        from acta.clab.cli import main as clab_main

        return int(clab_main(raw[1:]) or 0)

    parser = build_parser()
    args = parser.parse_args(raw)
    try:
        if args.command == "show":
            from acta.show_topo import run_show

            config = load_config(_PROJECT_DIR / ".config")
            host = args.host or config.get("CLAB_HOST") or None
            return run_show(
                args.topology,
                plain=args.plain,
                force_image=args.image,
                skip_probe=args.no_ssh,
                host=host,
                runtime=args.runtime,
            )
        if args.command == "ssh":
            from acta.ssh_node import run_ssh

            remote = list(args.remote_command or [])
            if remote and remote[0] == "--":
                remote = remote[1:]
            return run_ssh(
                args.node,
                runtime=args.runtime,
                command=remote or None,
            )
        if args.command == "attach":
            from acta.attach import run_attach

            run_attach(
                args.object_type,
                args.name,
                args.topology,
                to=args.to,
                mlag_pair=args.mlag_pair,
                mleaf=args.mleaf,
                et=args.et,
                project_dir=Path.cwd(),
            )
            return 0
        if args.command == "act":
            if args.act_command == "create":
                run_create(
                    Path.cwd(),
                    create_for=args.create_for,
                    clab_name=args.name,
                    clab_image=args.image,
                )
                return 0
            if args.act_command == "extend":
                return _run_extend(args)
            if args.act_command == "upload":
                return _run_upload(args)
            if args.act_command == "onboard":
                return _run_onboard()
            print(
                f"ERROR: act command {args.act_command!r} not implemented yet",
                flush=True,
            )
            return 2
    except (
        EOFError,
        FileNotFoundError,
        LookupError,
        NotImplementedError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        return 2
    print(f"ERROR: command {args.command!r} not implemented yet", flush=True)
    return 2

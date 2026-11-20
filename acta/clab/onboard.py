"""Onboard running cEOS labs to CVaaS."""

import base64
import getpass
import re
import subprocess
import sys
import time
from pathlib import Path

from .support import (
    CLI_ERROR,
    DOCKER_LIST_SCRIPT,
    DOCKER_SCRIPT,
    config_flag,
    config_ip_list,
    fail,
    host_run,
    inventory_hostname,
    mgmt_service_commands,
    parse_ipv4_list,
    read_config,
    validate_enrollment_token,
    validate_lab,
)


def check_onboarding_host(host, lab, runtime=None):
    hint = " Use --host user@lab-host if your lab runs remotely." if not host else ""
    expected = {f"clab-{lab['name']}-{node}" for node in lab["topology"]["nodes"]}
    candidates = {
        "docker": ("docker", "sudo-docker"),
        "podman": ("podman", "sudo-podman"),
    }.get(runtime, ("docker", "podman", "sudo-podman", "sudo-docker"))
    accessible = []
    errors = []
    for candidate in candidates:
        result = host_run(host, DOCKER_LIST_SCRIPT, [candidate], "")
        if result.returncode:
            if result.stderr.strip():
                errors.append(result.stderr.strip())
            continue
        running = set(result.stdout.splitlines())
        if expected <= running:
            return candidate
        accessible.append((len(expected & running), candidate, running))
    if not accessible:
        detail = errors[0] if errors else "Podman/Docker is unavailable."
        fail(
            f'Cannot inspect containers on {host or "the local machine"}: {detail}.{hint}'
        )
    _, candidate, running = max(accessible, key=lambda item: item[0])
    missing = sorted(expected - running)
    sample = ", ".join(missing[:5])
    more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
    fail(
        f"Missing {len(missing)}/{len(expected)} container(s) for lab {lab['name']} "
        f"on {host or 'the local machine'} ({candidate}): {sample}{more}. "
        f"Deploy the topology on this host first.{hint}"
    )


def wait_for_eos(host, container, attempts=30, delay=2.0, runtime="docker"):
    """Return True when Cli accepts enable/show version."""
    for _ in range(attempts):
        result = host_run(
            host, DOCKER_SCRIPT, [container, runtime], "enable\nshow version\n"
        )
        if result.returncode == 0 and not CLI_ERROR.search(result.stdout or ""):
            return True
        time.sleep(delay)
    return False


def onboard_node(host, container, commands, attempts=5, delay=3.0, runtime="docker"):
    """Push TerminAttr config with retries for slow cEOS boot."""
    last = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(delay)
        if not wait_for_eos(
            host, container, attempts=1 if attempt else 15, delay=delay, runtime=runtime
        ):
            last = subprocess.CompletedProcess(
                [], 1, "", f"EOS not ready in {container}"
            )
            continue
        result = host_run(host, DOCKER_SCRIPT, [container, runtime], commands)
        last = result
        if result.returncode == 0 and not CLI_ERROR.search(result.stdout or ""):
            return result
    return last


def enrollment_token(config):
    cached = (config.get("CVAAS_TOKEN") or "").strip()
    if cached:
        try:
            validate_enrollment_token(cached)
        except ValueError:
            print(
                "Cached CVaaS enrollment token is expired or invalid; enter a new token."
            )
        else:
            return cached
    token = getpass.getpass("CVaaS enrollment token: ").strip()
    if not token or "\n" in token or "\r" in token:
        fail("Enrollment token cannot be empty or contain newlines.")
    validate_enrollment_token(token)
    return token


def onboard(args):
    lab = validate_lab(Path(args.topology))
    runtime = check_onboarding_host(args.host, lab, getattr(args, "runtime", None))
    config = args.config if getattr(args, "config", None) is not None else read_config()
    endpoint = (
        args.endpoint
        or config.get("CVAAS_HOST")
        or input("CVaaS host (for example apiserver.arista.io): ").strip()
    )
    if not re.fullmatch(r"[A-Za-z0-9.-]+", endpoint):
        fail("Invalid CVaaS host.")
    token = enrollment_token(config)
    encoded = base64.b64encode(token.encode()).decode()
    disableaaa = (
        args.disableaaa
        if getattr(args, "disableaaa", None) is not None
        else config_flag(config.get("CLAB_DISABLEAAA"), default=False)
    )
    disableaaa_flag = " -disableaaa" if disableaaa else ""
    name_servers = parse_ipv4_list(
        config_ip_list(config, "CLAB_DNS", ["8.8.8.8", "1.1.1.1"]), "name-server"
    )
    ntp_servers = parse_ipv4_list(config_ip_list(config, "CLAB_NTP"), "ntp-server")
    print(
        f"Onboarding {len(lab['topology']['nodes'])} cEOS node(s) in {lab['name']} to {endpoint}."
    )
    if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Aborted.")
        return
    failures = []
    for node in lab["topology"]["nodes"]:
        container = f"clab-{lab['name']}-{node}"
        node_data = lab["topology"]["nodes"][node]
        env = node_data.get("env", {})
        hostname = inventory_hostname(lab["name"], node, node_data)
        mgmt_vrf = (
            env.get("CLAB_MGMT_VRF")
            if isinstance(env, dict) and env.get("CLAB_MGMT_VRF")
            else None
        )
        vrf_flag = f" -cvvrf={mgmt_vrf}" if mgmt_vrf else ""
        service_lines = mgmt_service_commands(
            name_servers, ntp_servers, mgmt_vrf=mgmt_vrf
        )
        service_block = ("\n".join(service_lines) + "\n") if service_lines else ""
        node_commands = (
            f"enable\nbash echo {encoded} > /tmp/cv-onboarding-token.b64\n"
            "bash base64 -d /tmp/cv-onboarding-token.b64 > /tmp/cv-onboarding-token\n"
            "bash rm -f /tmp/cv-onboarding-token.b64\n"
            f"configure terminal\nhostname {hostname}\n{service_block}"
            f"daemon TerminAttr\n   exec /usr/bin/TerminAttr -smashexcludes=ale,flexCounter,hardware,kni,pulse,strata -cvaddr={endpoint}:443 -cvauth=token-secure,/tmp/cv-onboarding-token{disableaaa_flag} -taillogs\n"
            "   shutdown\n   no shutdown\nend\nwrite memory\n"
        )
        node_commands = node_commands.replace(" -taillogs", vrf_flag + " -taillogs")
        result = onboard_node(args.host, container, node_commands, runtime=runtime)
        if result is None or result.returncode or CLI_ERROR.search(result.stdout or ""):
            failures.append(node)
            detail = ""
            if result is not None:
                detail = (
                    (result.stderr or "")
                    .strip()
                    .replace(token, "[redacted]")
                    .replace(encoded, "[redacted]")
                )
                if not detail:
                    errors = [
                        line.strip()
                        for line in (result.stdout or "").splitlines()
                        if CLI_ERROR.match(line)
                    ]
                    detail = (
                        "; ".join(errors)
                        .replace(token, "[redacted]")
                        .replace(encoded, "[redacted]")
                    )
            print(
                f"  {node}: failed"
                + (
                    f" ({detail})" if detail else " (check container and EOS readiness)"
                ),
                file=sys.stderr,
            )
        else:
            print(f"  {node}: configuration submitted")
    if failures:
        fail("Onboarding failed for: " + ", ".join(failures))
    print("Configuration submitted. Check CVaaS inventory to confirm registration.")

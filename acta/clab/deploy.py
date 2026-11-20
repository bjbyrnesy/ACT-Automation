"""Deploy generated containerlab labs."""

import sys
from pathlib import Path

from .generate import yaml_text
from .support import (
    ANNOTATION_SCRIPT,
    DEPLOY_SCRIPT,
    SUPPORT_SCRIPT,
    fail,
    host_run,
    resolve_topology_path,
    support_bundle,
    validate_lab,
    validate_network_name,
)


def deploy(args):
    path = resolve_topology_path(Path(args.topology), args)
    args.topology = str(path)
    lab = validate_lab(path)
    content = path.read_text()
    if args.mgmt_network:
        network = validate_network_name(args.mgmt_network)
        mgmt = lab.setdefault("mgmt", {})
        if not isinstance(mgmt, dict):
            fail("Invalid management network configuration.")
        mgmt["network"] = network
        content = yaml_text(lab)
    bundle = support_bundle(path.parent, lab)
    if bundle:
        result = host_run(args.host, SUPPORT_SCRIPT, [lab["name"]], bundle)
        if result.returncode:
            fail(f"Could not install lab support files: {result.stderr.strip()}")
    annotation_path = Path(str(path) + ".annotations.json")
    if annotation_path.is_file():
        result = host_run(
            args.host, ANNOTATION_SCRIPT, [lab["name"]], annotation_path.read_text()
        )
        if result.returncode:
            fail(f"Could not install viewer annotations: {result.stderr.strip()}")
        if result.stdout:
            print(result.stdout, end="")
    result = host_run(
        args.host,
        DEPLOY_SCRIPT,
        [lab["name"], getattr(args, "runtime", None) or "docker"],
        content,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode:
        fail(f"Deployment failed: {result.stderr.strip()}")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    print(f"Deployed {lab['name']}.")

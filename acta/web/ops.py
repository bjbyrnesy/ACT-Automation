"""In-process ops façade for the Web UI (clab / ACT / extend / attach).

Every wrapper calls the existing ``acta`` library code directly (no CLI
subprocess) and never blocks on stdin: interactive prompts either get a safe
default or fail with a clear error.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from acta.web.errors import WebError


def require_written_path(path: Path | None) -> Path:
    """Return *path* when it names a readable file, else raise ``WebError`` 400."""
    if path is None or str(path).strip() == "":
        raise WebError(400, "path is required", fields={"path": "required"})
    candidate = Path(path)
    if not candidate.is_file():
        raise WebError(
            400,
            f"file not found: {candidate}",
            fields={"path": "not a file"},
        )
    if not os.access(candidate, os.R_OK):
        raise WebError(
            400,
            f"file not readable: {candidate}",
            fields={"path": "not readable"},
        )
    return candidate


_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")
_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _check_tenant(tenant: str | None) -> None:
    """Reject tenants that could redirect credentials off ``*.act.arista.com``."""
    if tenant is not None and not _TENANT_RE.fullmatch(tenant):
        raise WebError(400, "invalid ACT tenant", fields={"tenant": "invalid"})


def _clab_args(topology: Path, **kwargs: Any) -> Any:
    """Build the argparse-like namespace the clab handlers expect."""
    from acta.clab.support import (
        DEFAULT_HOST_IMAGE,
        argparse_namespace,
        config_flag,
        config_image,
        config_ip_list,
        read_config,
    )

    config = read_config()
    runtime = (
        (config.get("CLAB_RUNTIME") or os.environ.get("CLAB_RUNTIME") or "")
        .strip()
        .lower()
    )
    if runtime not in {"docker", "podman"}:
        runtime = None
    values: dict[str, Any] = {
        "topology": str(topology),
        "source": str(topology),
        "host": config.get("CLAB_HOST") or None,
        "runtime": runtime,
        "from_act": config_flag(config.get("CLAB_FROM_ACT"), default=False),
        "name": config.get("CLAB_NAME") or None,
        "image": config_image(config),
        "host_image": config.get("CLAB_HOST_IMAGE") or DEFAULT_HOST_IMAGE,
        "config": config,
        "output": None,
        "mgmt_subnet": config.get("CLAB_MGMT_SUBNET") or "172.100.100.0/22",
        "mgmt_gateway": config.get("CLAB_MGMT_GATEWAY") or None,
        "mgmt_range": config.get("CLAB_MGMT_RANGE") or None,
        "mgmt_bridge": config.get("CLAB_MGMT_BRIDGE") or None,
        "mgmt_mtu": config.get("CLAB_MGMT_MTU") or None,
        "mgmt_network": config.get("CLAB_MGMT_NETWORK") or None,
        "name_servers": config_ip_list(config, "CLAB_DNS", ["8.8.8.8", "1.1.1.1"]),
        "ntp_servers": config_ip_list(config, "CLAB_NTP"),
        "endpoint": config.get("CVAAS_HOST") or None,
        "disableaaa": config_flag(config.get("CLAB_DISABLEAAA"), default=False),
    }
    for key, value in kwargs.items():
        if value is not None:
            values[key] = value
    return argparse_namespace(**values)


def op_clab_generate(act_path: Path, **kwargs: Any) -> Path:
    """Convert an ACT topology to a sibling ``.clab.yml`` and return its path."""
    from acta.clab.generate import generate

    source = require_written_path(act_path)
    # Output is always the sibling file; callers cannot redirect writes.
    kwargs["output"] = str(source.with_name(f"{source.stem}.clab.yml"))
    args = _clab_args(source, **kwargs)
    generate(args)
    return Path(args.output)


def op_clab_deploy(
    clab_or_act: Path, *, host: str | None = None, **kwargs: Any
) -> None:
    """Deploy a lab (``from_act`` is honoured for ACT input)."""
    from acta.clab.deploy import deploy

    source = require_written_path(clab_or_act)
    deploy(_clab_args(source, host=host, **kwargs))


def op_clab_destroy(
    clab_or_act: Path, *, host: str | None = None, **kwargs: Any
) -> None:
    """Destroy a deployed lab."""
    from acta.clab.destroy import destroy

    source = require_written_path(clab_or_act)
    destroy(_clab_args(source, host=host, **kwargs))


def op_clab_redeploy(
    clab_or_act: Path, *, host: str | None = None, **kwargs: Any
) -> None:
    """Destroy (if present) then deploy again."""
    from acta.clab.deploy import redeploy

    source = require_written_path(clab_or_act)
    redeploy(_clab_args(source, host=host, **kwargs))


def _no_prompt(prompt: str = "") -> str:
    """Stand-in for ``input`` in non-interactive web jobs."""
    if "Continue?" in prompt:
        return "y"  # the web request is the confirmation
    raise ValueError(f"interactive input is not available in the Web UI: {prompt!r}")


def op_clab_onboard(
    clab_or_act: Path, *, host: str | None = None, **kwargs: Any
) -> None:
    """Onboard cEOS nodes to CVaaS (auto-confirms; endpoint must be supplied)."""
    from acta.clab.onboard import onboard

    source = require_written_path(clab_or_act)
    args = _clab_args(source, host=host, **kwargs)
    with mock.patch("builtins.input", _no_prompt):
        onboard(args)


def _web_prompt_value(
    label: str, default: str | None = None, secret: bool = False
) -> str:
    if secret or default in (None, ""):
        raise ValueError(f"{label} is required (set it in .config or the environment)")
    return default


def op_act_upload(
    path: Path, *, deploy: bool = False, tenant: str | None = None, **kwargs: Any
) -> None:
    """Upload a topology to ACT, optionally creating and deploying a lab."""
    from acta.upload import run_upload

    topology = require_written_path(path)
    _check_tenant(tenant)
    with mock.patch("acta.upload.prompt_value", _web_prompt_value):
        run_upload(topology, deploy=deploy, tenant=tenant, **kwargs)


def op_act_onboard(**kwargs: Any) -> None:
    """Paste TerminAttr onboarding onto Running ACT lab devices.

    Accepts ``tenant``, ``user``, ``api_key``, ``cvaas_host``, ``cvaas_token``;
    each falls back to the environment, then the project ``.config``.
    """
    from acta.act_api import ActClient
    from acta.clab.support import validate_enrollment_token
    from acta.cli import _run_ssh_eos
    from acta.config import load_config
    from acta.onboard_act import CVAAS_PORT_DEFAULT, run_onboard_act
    from acta.upload import DEFAULT_ACT_TENANT, PROJECT_DIR

    config_file = PROJECT_DIR / ".config"
    config = load_config(config_file) if config_file.is_file() else {}

    def pick(key: str, env: str, default: str = "") -> str:
        return str(kwargs.get(key) or os.environ.get(env) or config.get(env) or default)

    if kwargs.get("cvaas_host") and not kwargs.get("cvaas_token"):
        raise WebError(
            400,
            "cvaas_host may only be supplied together with cvaas_token",
            fields={"cvaas_token": "required with cvaas_host"},
        )
    _check_tenant(kwargs.get("tenant"))
    tenant = pick("tenant", "ACT_TENANT", DEFAULT_ACT_TENANT)
    act_user = pick("user", "ACT_USER")
    api_key = pick("api_key", "ACT_API_KEY")
    cvaas_host = pick("cvaas_host", "CVAAS_HOST")
    cvaas_token = pick("cvaas_token", "CVAAS_TOKEN")
    for label, value in (
        ("ACT_USER", act_user),
        ("ACT_API_KEY", api_key),
        ("CVAAS_HOST", cvaas_host),
        ("CVAAS_TOKEN", cvaas_token),
    ):
        if not value:
            raise ValueError(f"{label} is required and cannot be blank")
    if not _HOST_RE.fullmatch(cvaas_host):
        raise WebError(400, "invalid CVaaS host", fields={"cvaas_host": "invalid"})
    validate_enrollment_token(cvaas_token)

    client = ActClient(f"https://{tenant}.act.arista.com/rest/v1", api_key)
    print(f"Logging into ACT ({tenant})...")
    client.login()
    run_onboard_act(
        client,
        act_user=act_user,
        cvaas_token=cvaas_token,
        cvaas_host=cvaas_host,
        cvaas_port=CVAAS_PORT_DEFAULT,
        run_ssh=_run_ssh_eos,
    )
    print("Done. TerminAttr onboarding commands pasted to Running lab devices.")


def op_extend(path: Path, **kwargs: Any) -> Path:
    """Extend an ACT topology and return the new dated file path.

    ``add`` is one of spine/leaf/pair/mleaf/site. Output is always a new dated
    file unless ``out`` is given; the source file is never modified.
    """
    from acta.extend import extend_topology
    from acta.site_extend import extend_add_site

    source = require_written_path(path)
    add = kwargs.pop("add", None)
    if not add:
        raise WebError(400, "add is required", fields={"add": "required"})
    out = kwargs.pop("out", None)
    out_path = Path(out) if out else None
    if add == "site":
        name = kwargs.pop("name", None)
        if not name:
            raise WebError(
                400, "name is required for site", fields={"name": "required"}
            )
        site_kwargs = {
            key: kwargs[key]
            for key in (
                "first_site",
                "rekey_identity",
                "bb_redundancy",
                "border_redundancy",
                "bb_count",
                "border_count",
                "force",
            )
            if kwargs.get(key) is not None
        }
        return extend_add_site(source, name, out=out_path, **site_kwargs).path
    return extend_topology(
        source,
        add,
        site=kwargs.get("site"),
        pair=kwargs.get("pair"),
        count=kwargs.get("count") or 1,
        out=out_path,
        new=out_path is None,
    ).path


@contextlib.contextmanager
def _quiet() -> Iterator[None]:
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        yield


def op_attach(path: Path, **kwargs: Any) -> Path:
    """Attach a generic host to a topology and return the updated file path."""
    from acta.attach import run_attach

    topology = require_written_path(path)
    host = kwargs.pop("host", None)
    if not host:
        raise WebError(400, "host is required", fields={"host": "required"})
    dual_homed = kwargs.get("dual_homed")
    if dual_homed is None:
        dual_homed = True
    with _quiet():
        result = run_attach(
            "host",
            host,
            topology,
            to=kwargs.get("to"),
            mlag_pair=kwargs.get("mlag_pair"),
            mleaf=kwargs.get("mleaf"),
            et=kwargs.get("et"),
            dual_homed=dual_homed,
            mlag_side=kwargs.get("mlag_side"),
            project_dir=topology.parent,
        )
    return result.path


def op_detach(path: Path, **kwargs: Any) -> Path:
    """Detach a generic host from a topology and return the updated file path."""
    from acta.attach import run_detach

    topology = require_written_path(path)
    host = kwargs.pop("host", None)
    if not host:
        raise WebError(400, "host is required", fields={"host": "required"})
    with _quiet():
        result = run_detach(
            "host",
            host,
            topology,
            project_dir=topology.parent,
        )
    return result.path

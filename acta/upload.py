from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml

from acta.act_api import ActClient
from acta.config import load_config, save_config
from acta.prompt import prompt_value

DEFAULT_ACT_TENANT = "ce"
POLL_INTERVAL = 10.0
TOPOLOGY_POLL_ITERATIONS = 30
LAB_POLL_ITERATIONS = 30
DEPLOY_POLL_ITERATIONS = 120
PROJECT_DIR = Path(__file__).resolve().parent.parent


class UploadError(RuntimeError):
    """Raised when an ACT upload step fails."""


def _is_operation(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("schema_type") == (
        "operation_resource"
    )


def _json_body(response: httpx.Response, action: str) -> Any:
    try:
        return response.json()
    except ValueError as error:
        snippet = response.text[:500]
        raise UploadError(
            f"ACT returned HTTP {response.status_code} with a non-JSON response "
            f"while {action}:\n{snippet}"
        ) from error


def _yaml_to_json(topology: Path) -> Any:
    try:
        return yaml.safe_load(topology.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise UploadError(f"could not parse {topology.name}: {error}") from error


def _attach_diagram(client: ActClient, topo_id: str, png: Path) -> None:
    """Best-effort diagram attach; never raises."""
    print(f"Attempting to attach diagram {png.name}...")
    try:
        response = client.request(
            "PATCH", f"topologies/{topo_id}", json={"diagram_path": png.name}
        )
        status = response.status_code
    except httpx.HTTPError as error:
        status = f"error ({error})"
    else:
        if 200 <= status < 300:
            print("  Diagram attached.")
            return
    print(f"  NOTE: Diagram upload returned HTTP {status}.")
    print("  The ACT REST API may not support diagram attachment via this")
    print("  method. Upload the PNG manually in the ACT web UI:")
    print("    Topologies -> Edit -> Diagram File -> Upload")
    print("  (The topology YAML was uploaded successfully.)")


def _lookup_existing(client: ActClient, name: str) -> tuple[str, str]:
    response = client.request(
        "GET", "topologies", params={"topology_pathname": name, "pageSize": 1}
    )
    body = _json_body(response, "looking up the existing topology")
    results = body.get("result") if isinstance(body, dict) else None
    first = results[0] if isinstance(results, list) and results else {}
    topo_id = first.get("id") or ""
    if not topo_id:
        raise UploadError(
            "could not look up the existing topology. "
            "Create a lab manually in the ACT UI."
        )
    return topo_id, first.get("topology_pathname") or ""


def _create_topology(client: ActClient, topology: Path, name: str) -> tuple[str, str]:
    payload = {
        "name": name,
        "description": f"Uploaded from {topology.name} by acta upload",
        "file": _yaml_to_json(topology),
    }
    response = client.request("POST", "topologies", json=payload)
    body = _json_body(response, "creating the topology")
    if not _is_operation(body):
        raise UploadError(f"ACT returned HTTP {response.status_code}: {body}")

    result = client.poll_operation_result(
        body,
        "topology creation",
        TOPOLOGY_POLL_ITERATIONS,
        POLL_INTERVAL,
    )
    status = str(result.get("status", "unknown")).casefold()
    detail = result.get("result")
    detail = detail if isinstance(detail, dict) else {}
    if status == "completed":
        topo_id = detail.get("id") or ""
        print(f"Created ACT topology '{detail.get('name') or name}'.")
        if topo_id:
            print(f"  Topology ID: {topo_id}")
        png = topology.with_suffix(".png")
        if png.is_file() and topo_id:
            print()
            _attach_diagram(client, topo_id, png)
        return topo_id, detail.get("topology_pathname") or ""

    message = detail.get("error") or result.get("error") or str(result)
    if "already exists" in str(message):
        # Fail closed: reusing the old topology would deploy stale contents
        # while implying the new YAML was uploaded.
        existing = ""
        try:
            existing_id, _ = _lookup_existing(client, name)
            existing = f" (existing ID: {existing_id})"
        except UploadError:
            pass
        raise UploadError(
            f"topology '{name}' already exists in ACT{existing} and was NOT "
            "updated with this YAML. Delete it in ACT or upload under a "
            "different name; refusing to create or deploy a lab from stale "
            "contents."
        )
    raise UploadError(f"topology creation failed: {message}")


def _create_and_deploy_lab(
    client: ActClient, topo_id: str, pathname: str, topology_name: str, lab_name: str
) -> None:
    if not pathname and topo_id:
        response = client.request("GET", f"topologies/{topo_id}")
        body = _json_body(response, "reading the topology")
        pathname = (
            body.get("topology_pathname") if isinstance(body, dict) else ""
        ) or ""
    if not pathname:
        raise UploadError(
            "could not determine topology_pathname from ACT. Create the lab "
            f"manually in the ACT UI using topology '{topology_name}'."
        )

    print(f"\nCreating lab '{lab_name}'...")
    response = client.request(
        "POST",
        "labs",
        json={
            "name": lab_name,
            "description": f"Created from {topology_name} by acta upload",
            "topology_definition": pathname,
        },
    )
    body = _json_body(response, "creating the lab")
    if not _is_operation(body):
        raise UploadError(f"unexpected response creating lab: {body}")
    result = client.poll_operation(
        body, "lab creation", LAB_POLL_ITERATIONS, POLL_INTERVAL
    )
    detail = result.get("result")
    lab_id = detail.get("id") if isinstance(detail, dict) else None
    if not lab_id:
        raise UploadError("ACT created the lab but didn't return its ID.")
    print(f"Created lab '{lab_name}' (ID: {lab_id}).")

    print(f"\nDeploying lab '{lab_name}'...")
    response = client.request("POST", f"labs/{lab_id}/deploy")
    body = _json_body(response, "deploying the lab")
    if not _is_operation(body):
        raise UploadError(f"unexpected response deploying lab: {body}")
    client.poll_operation(body, "lab deployment", DEPLOY_POLL_ITERATIONS, POLL_INTERVAL)
    print(f"Deployed lab '{lab_name}'.")


def _confirm(question: str) -> bool:
    answer = input(f"{question} [y/N] ").strip().casefold()
    return answer in {"y", "yes"}


def run_upload(
    topology: Path,
    *,
    deploy: bool | None = None,
    tenant: str | None = None,
    client: ActClient | None = None,
    project_dir: Path = PROJECT_DIR,
) -> None:
    """Upload a topology YAML to ACT and optionally create and deploy a lab.

    ``client`` and ``project_dir`` exist for testing; callers normally omit them.
    """
    topology = Path(topology)
    if not topology.is_file():
        raise FileNotFoundError(f"topology file not found: {topology}")

    config_path = project_dir / ".config"
    config = load_config(config_path)

    print("ACT topology upload:")
    if client is None:
        act_tenant = tenant or prompt_value(
            "ACT tenant",
            os.environ.get("ACT_TENANT")
            or config.get("ACT_TENANT")
            or DEFAULT_ACT_TENANT,
        )
        api_key = os.environ.get("ACT_API_KEY") or config.get("ACT_API_KEY")
        if not api_key:
            api_key = prompt_value("ACT API key", secret=True)
        config.update({"ACT_TENANT": act_tenant, "ACT_API_KEY": api_key})
        save_config(config_path, config)
        client = ActClient(f"https://{act_tenant}.act.arista.com/rest/v1", api_key)
    else:
        act_tenant = tenant or config.get("ACT_TENANT") or DEFAULT_ACT_TENANT

    topology_name = prompt_value("Topology name", topology.stem)

    print(f"\nLogging into ACT ({act_tenant})...")
    client.login()

    print(f"Uploading topology '{topology_name}' to {act_tenant}.act.arista.com...")
    topo_id, pathname = _create_topology(client, topology, topology_name)

    print()
    if deploy is None:
        deploy = _confirm("Create and deploy a lab from this topology?")
    if not deploy:
        print("Done. Deploy the topology in the ACT UI when ready, then run:")
        print("  acta.py act onboard")
        return

    default_lab = f"{topology_name.removesuffix('.yml').removesuffix('.yaml')}-lab"
    lab_name = prompt_value("Lab name", default_lab)
    _create_and_deploy_lab(client, topo_id, pathname, topology_name, lab_name)
    print("\nDone. Wait for the lab to reach Running state, then run:")
    print("  acta.py act onboard")

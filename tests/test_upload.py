import json

import httpx
import pytest

from acta import upload
from acta.act_api import ActClient

BASE = "https://tenant.example/rest/v1"
YAML_TEXT = "veos:\n  username: admin\nnodes:\n  - name: spine1\n"


def _op(op_id="op-1"):
    return {"schema_type": "operation_resource", "id": op_id}


def _done(result, status="Completed"):
    return {"id": "x", "is_completed": True, "status": status, "result": result}


class FakeAct:
    def __init__(self, extra=None):
        self.calls = []
        self.ops = {}
        self.extra = extra or {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/rest/v1")
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body, dict(request.url.params)))
        if path == "/auth/login":
            return httpx.Response(200, json={"token": "t"})
        if path.startswith("/operations/"):
            return httpx.Response(200, json=self.ops[path.rsplit("/", 1)[1]])
        key = (request.method, path)
        if key in self.extra:
            return self.extra[key](body)
        raise AssertionError(f"unexpected {key}")

    def client(self):
        return ActClient(BASE, "k", transport=httpx.MockTransport(self.handler))


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(upload, "POLL_INTERVAL", 0)
    monkeypatch.setattr(
        upload, "prompt_value", lambda label, default=None, secret=False: default
    )


@pytest.fixture
def topo(tmp_path):
    path = tmp_path / "fabric.yml"
    path.write_text(YAML_TEXT)
    return path


def _upload(fake, topo, tmp_path, **kwargs):
    upload.run_upload(
        topo, client=fake.client(), project_dir=tmp_path, tenant="tenant", **kwargs
    )


def test_uploads_topology_json_body_without_deploy(topo, tmp_path):
    fake = FakeAct()
    fake.ops["op-1"] = _done({"id": "T1", "name": "fabric", "topology_pathname": "p"})
    fake.extra[("POST", "/topologies")] = lambda body: httpx.Response(200, json=_op())

    _upload(fake, topo, tmp_path, deploy=False)

    post = next(c for c in fake.calls if c[:2] == ("POST", "/topologies"))
    assert post[2]["name"] == "fabric"
    assert post[2]["file"] == {
        "veos": {"username": "admin"},
        "nodes": [{"name": "spine1"}],
    }
    assert not any(c[1].startswith("/labs") for c in fake.calls)
    assert not any(c[0] == "PATCH" for c in fake.calls)


def test_png_sibling_attached_and_failure_is_tolerated(topo, tmp_path, capsys):
    topo.with_suffix(".png").write_bytes(b"png")
    fake = FakeAct()
    fake.ops["op-1"] = _done({"id": "T1", "topology_pathname": "p"})
    fake.extra[("POST", "/topologies")] = lambda body: httpx.Response(200, json=_op())
    fake.extra[("PATCH", "/topologies/T1")] = lambda body: httpx.Response(405, json={})

    _upload(fake, topo, tmp_path, deploy=False)

    patch = next(c for c in fake.calls if c[0] == "PATCH")
    assert patch[2] == {"diagram_path": "fabric.png"}
    assert "HTTP 405" in capsys.readouterr().out


def test_deploy_true_creates_and_deploys_lab(topo, tmp_path):
    fake = FakeAct()
    fake.ops["op-1"] = _done({"id": "T1", "topology_pathname": "path/fabric"})
    fake.ops["op-2"] = _done({"id": "L1"})
    fake.ops["op-3"] = _done({})
    fake.extra[("POST", "/topologies")] = lambda body: httpx.Response(200, json=_op())
    fake.extra[("POST", "/labs")] = lambda body: httpx.Response(200, json=_op("op-2"))
    fake.extra[("POST", "/labs/L1/deploy")] = lambda body: httpx.Response(
        200, json=_op("op-3")
    )

    _upload(fake, topo, tmp_path, deploy=True)

    lab = next(c for c in fake.calls if c[:2] == ("POST", "/labs"))
    assert lab[2]["name"] == "fabric-lab"
    assert lab[2]["topology_definition"] == "path/fabric"
    assert ("POST", "/labs/L1/deploy") in [c[:2] for c in fake.calls]


def test_existing_topology_is_looked_up(topo, tmp_path):
    fake = FakeAct()
    fake.ops["op-1"] = _done({"error": "name already exists"}, status="Failed")
    fake.extra[("POST", "/topologies")] = lambda body: httpx.Response(200, json=_op())
    fake.extra[("GET", "/topologies")] = lambda body: httpx.Response(
        200, json={"result": [{"id": "T9", "topology_pathname": "p9"}]}
    )

    _upload(fake, topo, tmp_path, deploy=False)

    lookup = next(c for c in fake.calls if c[:2] == ("GET", "/topologies"))
    assert lookup[3]["topology_pathname"] == "fabric"


def test_deploy_none_prompts(topo, tmp_path, monkeypatch):
    fake = FakeAct()
    fake.ops["op-1"] = _done({"id": "T1", "topology_pathname": "p"})
    fake.extra[("POST", "/topologies")] = lambda body: httpx.Response(200, json=_op())
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    _upload(fake, topo, tmp_path)

    assert not any(c[1].startswith("/labs") for c in fake.calls)


def test_other_failure_raises(topo, tmp_path):
    fake = FakeAct()
    fake.ops["op-1"] = _done({"error": "boom"}, status="Failed")
    fake.extra[("POST", "/topologies")] = lambda body: httpx.Response(200, json=_op())

    with pytest.raises(upload.UploadError, match="boom"):
        _upload(fake, topo, tmp_path, deploy=False)


def test_non_operation_response_raises(topo, tmp_path):
    fake = FakeAct()
    fake.extra[("POST", "/topologies")] = lambda body: httpx.Response(
        400, json={"error": "bad"}
    )

    with pytest.raises(upload.UploadError, match="HTTP 400"):
        _upload(fake, topo, tmp_path, deploy=False)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        upload.run_upload(tmp_path / "nope.yml", project_dir=tmp_path)

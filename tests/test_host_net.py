"""Unit tests for opt-in host data-plane addressing helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from acta.clab import host_net as hn


def test_next_host_ip_skips_network_gateway_broadcast_and_claimed():
    claimed = {"192.168.2.2", "192.168.2.3"}
    assert hn.next_host_ip("192.168.2.0/24", "192.168.2.1", claimed) == "192.168.2.4"


def test_validate_rejects_gateway_outside_subnet():
    with pytest.raises(ValueError, match="gateway"):
        hn.validate_host_net("192.168.2.0/24", "10.0.0.1", None)


def test_validate_rejects_host_ip_equal_gateway():
    with pytest.raises(ValueError, match="gateway"):
        hn.validate_host_net("192.168.2.0/24", "192.168.2.1", "192.168.2.1")


def test_resolve_disabled_returns_none():
    assert (
        hn.resolve_host_net(
            enabled=False,
            host_ip=None,
            host_subnet=None,
            host_gateway=None,
            config={},
            claimed=set(),
            dual_homed=False,
        )
        is None
    )


def test_resolve_auto_allocates_and_picks_iface():
    plan = hn.resolve_host_net(
        enabled=True,
        host_ip=None,
        host_subnet=None,
        host_gateway=None,
        config={},
        claimed=set(),
        dual_homed=True,
    )
    assert plan is not None
    assert plan.ip == "192.168.2.2"
    assert plan.subnet == "192.168.2.0/24"
    assert plan.gateway == "192.168.2.1"
    assert plan.iface == "bond0"
    assert plan.dual_homed is True


def test_claimed_ips_from_clab_labels():
    lab = {
        "topology": {
            "nodes": {
                "h1": {
                    "kind": "linux",
                    "labels": {
                        "acta.host-net": "true",
                        "acta.host-ip": "192.168.2.2",
                    },
                },
                "leaf1": {"kind": "ceos"},
            }
        }
    }
    assert hn.claimed_ips_from_clab(lab) == {"192.168.2.2"}


def test_validate_rejects_ipv6_and_reserved_addresses():
    with pytest.raises(ValueError, match="IPv4"):
        hn.validate_host_net("2001:db8::/64", "2001:db8::1", None)
    with pytest.raises(ValueError, match="gateway"):
        hn.validate_host_net("192.168.2.0/24", "::1", None)
    with pytest.raises(ValueError, match="gateway"):
        hn.validate_host_net("192.168.2.0/24", "192.168.2.0", None)
    with pytest.raises(ValueError, match="gateway"):
        hn.validate_host_net("192.168.2.0/24", "192.168.2.255", None)
    with pytest.raises(ValueError, match="host IP"):
        hn.validate_host_net("192.168.2.0/24", "192.168.2.1", "::1")
    with pytest.raises(ValueError, match="host IP"):
        hn.validate_host_net("192.168.2.0/24", "192.168.2.1", "10.0.0.5")
    with pytest.raises(ValueError, match="host IP"):
        hn.validate_host_net("192.168.2.0/24", "192.168.2.1", "192.168.2.255")


def test_next_host_ip_exhausted_raises():
    with pytest.raises(ValueError, match="no free host addresses"):
        hn.next_host_ip("192.168.2.0/30", "192.168.2.1", {"192.168.2.2"})


def test_resolve_single_homed_config_defaults_and_conflict():
    plan = hn.resolve_host_net(
        enabled=True,
        host_ip="10.20.30.10",
        host_subnet=None,
        host_gateway=None,
        config={
            "HOST_NET_SUBNET": "10.20.30.0/24",
            "HOST_NET_GATEWAY": "10.20.30.1",
        },
        claimed=set(),
        dual_homed=False,
    )
    assert plan is not None
    assert plan.ip == "10.20.30.10"
    assert plan.prefixlen == 24
    assert plan.iface == "eth1"
    assert plan.dual_homed is False

    with pytest.raises(ValueError, match="already in use"):
        hn.resolve_host_net(
            enabled=True,
            host_ip="10.20.30.10",
            host_subnet="10.20.30.0/24",
            host_gateway="10.20.30.1",
            config=None,
            claimed={"10.20.30.10"},
            dual_homed=False,
        )


def test_claimed_ips_strips_cidr_and_ignores_disabled_or_malformed():
    lab = {
        "topology": {
            "nodes": {
                "h1": {
                    "labels": {
                        "acta.host-net": "1",
                        "acta.host-ip": "192.168.2.5/24",
                    }
                },
                "h2": {
                    "labels": {
                        "acta.host-net": "false",
                        "acta.host-ip": "192.168.2.6",
                    }
                },
                "bad": "not-a-dict",
            }
        }
    }
    assert hn.claimed_ips_from_clab(lab) == {"192.168.2.5"}
    assert hn.claimed_ips_from_clab({"topology": {"nodes": []}}) == set()


def _single() -> hn.HostNetPlan:
    return hn.HostNetPlan(
        ip="192.168.2.10",
        subnet="192.168.2.0/24",
        gateway="192.168.2.1",
        iface="eth1",
        dual_homed=False,
    )


def _dual() -> hn.HostNetPlan:
    return hn.HostNetPlan(
        ip="192.168.2.11",
        subnet="192.168.2.0/24",
        gateway="192.168.2.1",
        iface="bond0",
        dual_homed=True,
    )


def test_render_bootstrap_single_uses_eth1():
    script = hn.render_bootstrap(_single())
    assert script.startswith("#!/bin/sh")
    assert "set -eu" in script
    assert "eth1" in script
    assert "192.168.2.10/24" in script
    assert "ip route replace default via 192.168.2.1 dev eth1" in script
    assert "bond0" not in script


def test_render_bootstrap_dual_creates_lacp_bond():
    script = hn.render_bootstrap(_dual())
    assert "mode 802.3ad" in script or "mode=802.3ad" in script
    assert "eth1" in script and "eth2" in script
    assert "bond0" in script
    assert "192.168.2.11/24" in script
    assert "ip route replace default via 192.168.2.1 dev bond0" in script


def test_render_md_mentions_mcast_and_cloudvision():
    md = hn.render_host_net_md(_single(), host="host1")
    assert "mcast-send" in md
    assert "CloudVision" in md
    assert "192.168.2.10" in md


def test_render_md_lists_tools_and_dual_lacp():
    md = hn.render_host_net_md(_dual(), host="host2")
    for tool in (
        "ping",
        "traceroute",
        "curl",
        "dig",
        "lldpcli",
        "mcast-send",
        "mcast-receive",
        "mcast-status",
    ):
        assert tool in md
    assert "LACP" in md
    assert "bond0" in md


def test_render_env_and_labels():
    plan = _single()
    env = hn.render_host_net_env(plan)
    assert "HOST_NET_IP=192.168.2.10" in env
    assert "HOST_NET_IFACE=eth1" in env
    assert hn.host_net_labels(plan) == {
        hn.LABEL_ENABLED: "true",
        hn.LABEL_IP: "192.168.2.10",
        hn.LABEL_SUBNET: "192.168.2.0/24",
        hn.LABEL_GATEWAY: "192.168.2.1",
        hn.LABEL_IFACE: "eth1",
    }


def test_write_host_net_files(tmp_path: Path):
    boot, md, env = hn.write_host_net_files(tmp_path, "host1", _single())
    assert boot.parent == tmp_path / "host1"
    assert (boot.name, md.name, env.name) == (
        "bootstrap.sh",
        "HOST-NET.md",
        "HOST-NET.env",
    )
    assert boot.stat().st_mode & 0o111
    assert "192.168.2.10" in md.read_text()
    assert "HOST_NET_IP" in env.read_text()


@pytest.mark.parametrize(
    ("name", "stem"),
    [
        ("demo.clab.yml", "demo"),
        ("demo.clab.yaml", "demo"),
        ("demo.yml", "demo"),
        ("demo.yaml", "demo"),
        ("demo", "demo"),
    ],
)
def test_host_net_artifact_dir(tmp_path: Path, name: str, stem: str):
    assert hn.host_net_artifact_dir(tmp_path / name, "h1") == (
        tmp_path / f"{stem}.host-net" / "h1"
    )


def test_linux_jumphost_node_without_host_net_unchanged():
    from acta.clab.support import linux_jumphost_node

    node = linux_jumphost_node("img:tag", mgmt_ipv4="172.100.100.10")
    assert node["exec"] == ["lldpd"]
    assert "binds" not in node
    assert "labels" not in node


def test_linux_jumphost_node_includes_host_net_binds(tmp_path: Path):
    from acta.clab.support import linux_jumphost_node

    clab = tmp_path / "lab.clab.yml"
    clab.write_text("name: lab\n")
    plan = hn.HostNetPlan("192.168.2.5", "192.168.2.0/24", "192.168.2.1", "eth1", False)
    d = hn.host_net_artifact_dir(clab, "h1")
    hn.write_host_net_files(d.parent, "h1", plan)
    node = linux_jumphost_node(
        "img:tag", mgmt_ipv4="172.100.100.10", host_net=plan, host_net_dir=d
    )
    assert node["labels"]["acta.host-ip"] == "192.168.2.5"
    assert node["exec"] == ["lldpd", "sh /etc/acta-host-net/bootstrap.sh"]
    assert node["binds"] == [
        f"{d}/bootstrap.sh:/etc/acta-host-net/bootstrap.sh:ro",
        f"{d}/HOST-NET.md:/root/HOST-NET.md:ro",
        f"{d}/HOST-NET.env:/root/HOST-NET.env:ro",
    ]
    assert node["mgmt-ipv4"] == "172.100.100.10"


def test_linux_jumphost_node_host_net_requires_dir():
    from acta.clab.support import linux_jumphost_node

    plan = hn.HostNetPlan("192.168.2.5", "192.168.2.0/24", "192.168.2.1", "eth1", False)
    with pytest.raises(ValueError, match="host_net_dir"):
        linux_jumphost_node("img:tag", host_net=plan)


def test_claimed_ips_skips_null_non_str_and_malformed_ips():
    lab = {
        "topology": {
            "nodes": {
                "null": {"labels": {"acta.host-net": "true", "acta.host-ip": None}},
                "int": {"labels": {"acta.host-net": True, "acta.host-ip": 7}},
                "junk": {"labels": {"acta.host-net": "true", "acta.host-ip": "nope"}},
                "ok": {
                    "labels": {"acta.host-net": True, "acta.host-ip": "192.168.2.4"}
                },
            }
        }
    }
    assert hn.claimed_ips_from_clab(lab) == {"192.168.2.4"}
    assert hn.next_host_ip("192.168.2.0/24", "192.168.2.1", set()) == "192.168.2.2"


def test_resolve_blank_overrides_and_settings_fall_back_to_defaults():
    plan = hn.resolve_host_net(
        enabled=True,
        host_ip="  ",
        host_subnet=" ",
        host_gateway="",
        config={"HOST_NET_SUBNET": "   ", "HOST_NET_GATEWAY": "\t"},
        claimed=set(),
        dual_homed=False,
    )
    assert plan is not None
    assert (plan.ip, plan.subnet, plan.gateway) == (
        "192.168.2.2",
        hn.DEFAULT_HOST_NET_SUBNET,
        hn.DEFAULT_HOST_NET_GATEWAY,
    )


def test_render_md_flushes_before_changing_ip():
    md = hn.render_host_net_md(_single(), host="host1")
    assert "ip -4 addr flush dev eth1" in md
    assert "ip addr replace <new-ip>" not in md


def test_host_net_bind_dir_is_relative(tmp_path: Path):
    rel = hn.host_net_bind_dir(tmp_path / "demo.clab.yml", "h1")
    assert not rel.is_absolute()
    assert rel.as_posix() == "demo.host-net/h1"


def test_plan_from_labels_round_trips_and_follows_homing():
    labels = hn.host_net_labels(_single())
    assert hn.plan_from_labels(labels, dual_homed=False) == _single()
    dual = hn.plan_from_labels(labels, dual_homed=True)
    assert (dual.iface, dual.dual_homed, dual.ip) == ("bond0", True, "192.168.2.10")
    with pytest.raises(ValueError, match="acta.host-ip"):
        hn.plan_from_labels({"acta.host-net": "true"}, dual_homed=False)


def test_host_net_bind_sources_only_relative_enabled_nodes():
    from acta.clab.support import linux_jumphost_node

    rel = hn.host_net_bind_dir(Path("demo.clab.yml"), "h1")
    lab = {
        "topology": {
            "nodes": {
                "h1": linux_jumphost_node("img", host_net=_single(), host_net_dir=rel),
                "abs": {
                    "labels": {"acta.host-net": "true"},
                    "binds": ["/Users/x/demo.host-net/abs/bootstrap.sh:/b:ro"],
                },
                "off": {"binds": ["demo.host-net/off/bootstrap.sh:/b:ro"]},
            }
        }
    }
    assert hn.host_net_bind_sources(lab) == [
        "demo.host-net/h1/bootstrap.sh",
        "demo.host-net/h1/HOST-NET.md",
        "demo.host-net/h1/HOST-NET.env",
    ]

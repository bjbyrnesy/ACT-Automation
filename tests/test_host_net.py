"""Unit tests for opt-in host data-plane addressing helpers."""

from __future__ import annotations

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

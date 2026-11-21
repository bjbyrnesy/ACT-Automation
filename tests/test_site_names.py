import pytest

from acta.site_names import (
    HOSTNAME_HARD_CAP,
    MAX_SITES,
    SITE_SOFT_CAP,
    backbone_hostname,
    fabric_hostname,
    fabric_prefix_from_names,
    hostname_prefix_of,
    parse_fabric_identity,
    validate_site_token,
)


def test_max_sites_is_eight():
    assert MAX_SITES == 8


def test_validate_site_accepts_airport_and_legacy_letters():
    assert validate_site_token("aus") == "aus"
    assert validate_site_token("dfw-campus") == "dfw-campus"
    assert validate_site_token("A") == "A"
    assert validate_site_token("site_b") == "site_b"


def test_validate_site_rejects_bad_charset_and_soft_cap():
    with pytest.raises(ValueError, match="alphanumeric"):
        validate_site_token("bad.name")
    with pytest.raises(ValueError, match="empty"):
        validate_site_token("  ")
    with pytest.raises(ValueError, match="soft-cap"):
        validate_site_token("a" * (SITE_SOFT_CAP + 1))


def test_fabric_hostname_enforces_hard_cap():
    name = fabric_hostname("blz2", "aus", "spine1")
    assert name == "blz2-aus-spine1"
    assert len(name) <= HOSTNAME_HARD_CAP
    with pytest.raises(ValueError, match=str(HOSTNAME_HARD_CAP)):
        fabric_hostname("p" * 40, "s" * 32, "spine1")


def test_backbone_hostname():
    assert backbone_hostname("blz2", 1) == "blz2-bb1"
    with pytest.raises(ValueError, match=">= 1"):
        backbone_hostname("blz2", 0)


def test_parse_hyphenated_prefix_stays_single_site_without_prefix():
    assert parse_fabric_identity("my-lab-spine1") == (None, "spine", 1)
    assert hostname_prefix_of("my-lab-spine1") == "my-lab"


def test_parse_named_site_needs_known_prefix():
    assert parse_fabric_identity("my-lab-aus-spine1") == (None, "spine", 1)
    assert parse_fabric_identity("my-lab-aus-spine1", prefix="my-lab") == (
        "aus",
        "spine",
        1,
    )
    assert parse_fabric_identity("my-lab-spine1", prefix="my-lab") == (
        None,
        "spine",
        1,
    )
    assert parse_fabric_identity("my-lab-bb1", prefix="my-lab") == (None, "bb", 1)
    assert parse_fabric_identity("demo-A-spine1", prefix="demo") == ("A", "spine", 1)
    assert parse_fabric_identity("blz3-mso-leaf2", prefix="blz3") == (
        "mso",
        "leaf",
        2,
    )


def test_fabric_prefix_from_names_prefers_backbone():
    assert (
        fabric_prefix_from_names(
            ["demo-A-spine1", "demo-A-leaf1", "demo-bb1", "demo-bb2"]
        )
        == "demo"
    )
    assert fabric_prefix_from_names(["my-lab-aus-spine1", "my-lab-bb1"]) == "my-lab"
    assert fabric_prefix_from_names(["my-lab-spine1", "my-lab-leaf1"]) == "my-lab"

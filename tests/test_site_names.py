import pytest

from acta.site_names import (
    HOSTNAME_HARD_CAP,
    MAX_SITES,
    SITE_SOFT_CAP,
    backbone_hostname,
    fabric_hostname,
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

"""Site token and hostname rules for multi-DC topologies."""

from __future__ import annotations

import re
from collections.abc import Iterable

MAX_SITES = 8
SITE_SOFT_CAP = 32
HOSTNAME_HARD_CAP = 64

_SITE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# Named or letter sites: ``{prefix}-{site}-{role}{n}`` (site may contain -/_).
_MULTI_FABRIC_RE = re.compile(
    r"-(?P<site>[A-Za-z0-9][A-Za-z0-9_-]*)-"
    r"(?P<role>border|spine|leaf|mleaf)(?P<index>[1-9]\d*)$"
)
_BB_RE = re.compile(r"-bb(?P<index>[1-9]\d*)$")
_SINGLE_FABRIC_RE = re.compile(
    r"-(?P<role>border|spine|leaf|mleaf)(?P<index>[1-9]\d*)$"
)
_BB_SUFFIX_RE = re.compile(r"^bb(?P<index>[1-9]\d*)$")
_FABRIC_SUFFIX_RE = re.compile(
    r"^(?:(?P<site>[A-Za-z0-9][A-Za-z0-9_-]*)-)?"
    r"(?P<role>border|spine|leaf|mleaf)(?P<index>[1-9]\d*)$"
)


def validate_site_token(site: str) -> str:
    """Return a validated site token (soft-cap 32; charset alnum/_/-)."""
    token = site.strip()
    if not token:
        raise ValueError("site name must not be empty")
    if not _SITE_RE.fullmatch(token):
        raise ValueError(
            "site name must be alphanumeric with optional internal "
            "hyphens/underscores (e.g. aus, dfw-campus)"
        )
    if token.startswith(("-", "_")):
        raise ValueError("site name must not start with a hyphen or underscore")
    if token.endswith(("-", "_")):
        raise ValueError("site name must not end with a hyphen or underscore")
    if len(token) > SITE_SOFT_CAP:
        raise ValueError(
            f"site name soft-cap is {SITE_SOFT_CAP} characters "
            f"(got {len(token)}; shorten for readability)"
        )
    return token


def fabric_hostname(prefix: str, site: str | None, role_index: str) -> str:
    """Build ``{prefix}-{site}-{role}{n}`` or single-site ``{prefix}-{role}{n}``."""
    if site is None:
        name = f"{prefix}-{role_index}"
    else:
        token = validate_site_token(site)
        name = f"{prefix}-{token}-{role_index}"
    if len(name) > HOSTNAME_HARD_CAP:
        raise ValueError(
            f"hostname exceeds {HOSTNAME_HARD_CAP} characters "
            f"({name!r} is {len(name)} chars); shorten prefix or site"
        )
    return name


def backbone_hostname(prefix: str, index: int) -> str:
    """Build ``{prefix}-bb{n}`` with the hostname length hard-cap."""
    if index < 1:
        raise ValueError("backbone index must be >= 1")
    name = f"{prefix}-bb{index}"
    if len(name) > HOSTNAME_HARD_CAP:
        raise ValueError(
            f"hostname exceeds {HOSTNAME_HARD_CAP} characters "
            f"({name!r} is {len(name)} chars); shorten prefix"
        )
    return name


def _parse_suffix(rest: str) -> tuple[str | None, str, int] | None:
    """Parse ``bbN``, ``roleN``, or ``site-roleN`` after a known prefix."""
    bb = _BB_SUFFIX_RE.fullmatch(rest)
    if bb is not None:
        return None, "bb", int(bb.group("index"))
    fabric = _FABRIC_SUFFIX_RE.fullmatch(rest)
    if fabric is not None:
        return (
            fabric.group("site"),
            fabric.group("role"),
            int(fabric.group("index")),
        )
    return None


def parse_fabric_identity(
    hostname: str, *, prefix: str | None = None
) -> tuple[str | None, str, int] | None:
    """Return ``(site|None, role, index)`` from an ACT fabric hostname.

    When ``prefix`` is known (from a ``*-bbN`` node or the caller), hyphenated
    prefixes disambiguate: ``my-lab-spine1`` is single-site and
    ``my-lab-aus-spine1`` yields site ``aus``.

    Without ``prefix``, backbone wins, then single-site role suffix. Named
    multi-site hostnames need ``prefix`` so ``lab`` in ``my-lab-spine1`` is not
    mistaken for a site token.
    """
    if prefix is not None:
        head = f"{prefix}-"
        if not hostname.startswith(head):
            return None
        return _parse_suffix(hostname[len(head) :])

    bb = _BB_RE.search(hostname)
    if bb is not None:
        return None, "bb", int(bb.group("index"))
    single = _SINGLE_FABRIC_RE.search(hostname)
    if single is not None:
        return None, single.group("role"), int(single.group("index"))
    return None


def hostname_prefix_of(hostname: str, *, prefix: str | None = None) -> str:
    """Strip site/role/index (or bb index) suffix from a fabric hostname.

    Prefer an explicit ``prefix`` when known. Otherwise prefer backbone, then
    single-site role strip (hyphenated prefixes like ``my-lab-spine1``).
    """
    if prefix is not None:
        head = f"{prefix}-"
        if hostname.startswith(head):
            return prefix
    bb = _BB_RE.search(hostname)
    if bb is not None:
        return hostname[: bb.start()]
    single = _SINGLE_FABRIC_RE.search(hostname)
    if single is not None:
        return hostname[: single.start()]
    multi = _MULTI_FABRIC_RE.search(hostname)
    if multi is not None:
        return hostname[: multi.start()]
    return hostname


def fabric_prefix_from_names(names: Iterable[str]) -> str | None:
    """Detect lab hostname prefix, preferring ``*-bbN`` over fabric nodes."""
    fallback: str | None = None
    for name in names:
        bb = _BB_RE.search(name)
        if bb is not None:
            return name[: bb.start()]
        if fallback is None:
            single = _SINGLE_FABRIC_RE.search(name)
            if single is not None:
                fallback = name[: single.start()]
    return fallback


def dot_safe_id(token: str) -> str:
    """Sanitize a site/host token for Graphviz node/cluster ids."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", token)
    if not safe:
        return "x"
    if not safe[0].isalpha():
        return f"n_{safe}"
    return safe

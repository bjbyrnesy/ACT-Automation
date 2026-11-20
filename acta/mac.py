from __future__ import annotations

import hashlib


def generate_mac(serial_prefix: str, hostname: str) -> str:
    """Return the stable Arista-OUI MAC used by the topology generator."""
    digest = hashlib.sha256(f"{serial_prefix}-{hostname}".encode()).hexdigest()[:6]
    suffix = ":".join(digest[index : index + 2] for index in range(0, 6, 2))
    return f"00:1c:73:{suffix}"

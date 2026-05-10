"""Per-make adapter registry.

The orchestrator looks up a make name (case-insensitive) in
:data:`REGISTRY` and dispatches to that adapter's :meth:`lookup`.
"""
from __future__ import annotations

from .base import (
    MakerAdapter,
    MakerError,
    MakerLookup,
    MakerLoginRequired,
    MakerUnsupported,
)
from .chevrolet import ChevroletAdapter
from .ford import FordAdapter
from .gmc import GmcAdapter
from .honda import HondaAdapter
from .jeep import JeepAdapter
from .ram import RamAdapter
from .toyota import ToyotaAdapter

REGISTRY: dict[str, MakerAdapter] = {
    "Ford": FordAdapter(),
    "Toyota": ToyotaAdapter(),
    "Honda": HondaAdapter(),
    "Chevrolet": ChevroletAdapter(),
    "GMC": GmcAdapter(),
    "Jeep": JeepAdapter(),
    "Ram": RamAdapter(),
}


def get_adapter(make: str | None) -> MakerAdapter | None:
    if not make:
        return None
    # case/whitespace-insensitive match
    target = make.strip().lower()
    for k, v in REGISTRY.items():
        if k.lower() == target:
            return v
    return None


__all__ = [
    "MakerAdapter",
    "MakerError",
    "MakerLookup",
    "MakerLoginRequired",
    "MakerUnsupported",
    "REGISTRY",
    "get_adapter",
]

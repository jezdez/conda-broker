"""Service supervision for long-running conda-adjacent processes."""

from __future__ import annotations

from ._version import __version__
from .api import (
    Broker,
    BrokerContext,
    BrokerState,
    Service,
    ServiceCheck,
    ServiceContext,
    StatusSnapshot,
)

__all__ = [
    "Broker",
    "BrokerContext",
    "BrokerState",
    "Service",
    "ServiceCheck",
    "ServiceContext",
    "StatusSnapshot",
    "__version__",
]

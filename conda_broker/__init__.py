"""Service supervision for long-running conda-adjacent processes."""

from __future__ import annotations

from .api import (
    Broker,
    BrokerContext,
    BrokerState,
    Service,
    ServiceContext,
    StatusSnapshot,
)

__all__ = [
    "Broker",
    "BrokerContext",
    "BrokerState",
    "Service",
    "ServiceContext",
    "StatusSnapshot",
    "__version__",
]

__version__ = "0.1.0"

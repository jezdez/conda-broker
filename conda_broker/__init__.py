"""Service supervision for long-running conda-adjacent processes."""

from __future__ import annotations

from .api import Broker, BrokerState, Service, StatusSnapshot

__all__ = ["Broker", "BrokerState", "Service", "StatusSnapshot", "__version__"]

__version__ = "0.1.0"

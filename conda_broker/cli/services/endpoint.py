"""Implementation of ``conda broker endpoint``."""

from __future__ import annotations

from ... import Broker
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_endpoint(args, *, console=None) -> int:
    paths = ServicePaths.resolve(args.runtime_dir, args.log_dir)
    snapshot = Broker.current(paths).status(args.service)
    status = snapshot.services[0] if snapshot.services else None
    selected = status.endpoint(args.endpoint) if status else None
    payload = {
        "service": args.service,
        "endpoint_name": args.endpoint,
        "endpoint": selected.to_dict() if selected else None,
        "endpoints": status.endpoints if status else {},
        "ready": bool(status and status.ready),
    }
    BrokerConsole(console).emit(args, payload)
    return 0 if selected else 1

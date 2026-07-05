"""Implementation of ``conda broker endpoint``."""

from __future__ import annotations

from ... import Broker
from .common import emit_payload, paths_from_args


def execute_endpoint(args, *, console=None) -> int:
    snapshot = Broker.current(paths_from_args(args)).status(args.service)
    status = snapshot.services[0] if snapshot.services else None
    selected = status.endpoint(args.endpoint) if status else None
    payload = {
        "service": args.service,
        "endpoint_name": args.endpoint,
        "endpoint": selected.to_dict() if selected else None,
        "endpoints": status.endpoints if status else {},
        "ready": bool(status and status.ready),
    }
    emit_payload(args, payload, console=console)
    return 0 if selected else 1

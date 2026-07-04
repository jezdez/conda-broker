"""Implementation of ``conda broker endpoint``."""

from __future__ import annotations

from ... import client
from .common import emit_payload, paths_from_args


def execute_endpoint(args, *, console=None) -> int:
    payload = client.status(args.service, paths=paths_from_args(args))
    services = payload.get("services")
    status = services[0] if isinstance(services, list) and services else None
    endpoints = {}
    selected = None
    if status and isinstance(status.get("endpoints"), dict):
        endpoints = status["endpoints"]
        value = endpoints.get(args.endpoint)
        selected = value if isinstance(value, dict) else None
    payload = {
        "service": args.service,
        "endpoint_name": args.endpoint,
        "endpoint": selected,
        "endpoints": endpoints,
        "ready": bool(status and status.get("ready")),
    }
    emit_payload(args, payload, console=console)
    return 0 if selected else 1

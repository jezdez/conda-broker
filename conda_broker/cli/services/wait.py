"""Implementation of ``conda broker wait``."""

from __future__ import annotations

from ... import client
from .common import emit_payload, paths_from_args


def execute_wait(args, *, console=None) -> int:
    payload = client.wait(
        args.service,
        paths=paths_from_args(args),
        timeout_s=args.timeout,
        start_service=args.start,
    )
    emit_payload(args, payload, console=console)
    services = payload.get("services")
    if not isinstance(services, list) or not services:
        return 1
    service = services[0]
    return 0 if isinstance(service, dict) and service.get("ready") else 1

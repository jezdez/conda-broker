"""Implementation of ``conda broker wait``."""

from __future__ import annotations

from ... import Broker
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_wait(args, *, console=None) -> int:
    payload = (
        Broker.current(ServicePaths.resolve(args.runtime_dir, args.log_dir))
        .service(args.service)
        .wait(timeout_s=args.timeout, start=args.start)
        .to_dict()
    )
    BrokerConsole(console).emit(args, payload)
    services = payload.get("services")
    if not isinstance(services, list) or not services:
        return 1
    service = services[0]
    return 0 if isinstance(service, dict) and service.get("ready") else 1

"""Implementation of ``conda broker stop``."""

from __future__ import annotations

from ... import Broker
from ...exceptions import UnknownServiceError
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_stop(args, *, console=None) -> int:
    broker = Broker.current(ServicePaths.resolve(args.runtime_dir, args.log_dir))
    if args.services and broker.running():
        payload = broker.stop_services(tuple(args.services)).to_dict()
    elif args.services:
        snapshot = broker.status()
        selected = set(args.services)
        found = {service.name for service in snapshot.services}
        missing = sorted(selected - found)
        if missing:
            raise UnknownServiceError(f"Unknown service: {missing[0]}")
        payload = snapshot.to_dict()
        payload["services"] = [
            service.to_dict()
            for service in snapshot.services
            if service.name in selected
        ]
    elif broker.running():
        payload = broker.stop()
    else:
        payload = {"broker": {"running": False, "stopping": False}}
    BrokerConsole(console).emit(args, payload)
    return 0

"""Implementation of ``conda broker restart``."""

from __future__ import annotations

from ... import Broker
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_restart(args, *, console=None) -> int:
    broker = Broker.current(ServicePaths.resolve(args.runtime_dir, args.log_dir))
    if args.services:
        payload = broker.restart_services(
            tuple(args.services),
            timeout_s=args.timeout,
        ).to_dict()
    else:
        payload = {"broker": broker.restart(timeout_s=args.timeout).to_dict()}
    BrokerConsole(console).emit(args, payload)
    return 0

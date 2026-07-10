"""Implementation of ``conda broker start``."""

from __future__ import annotations

from ... import Broker
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_start(args, *, console=None) -> int:
    broker = Broker.current(ServicePaths.resolve(args.runtime_dir, args.log_dir))
    if args.services:
        payload = broker.start_services(
            tuple(args.services),
            timeout_s=args.timeout,
        ).to_dict()
    else:
        broker_state = broker.start(timeout_s=args.timeout)
        payload = broker.status().to_dict()
        payload["broker"] = broker_state.to_dict()
    BrokerConsole(console).emit(args, payload)
    return 0

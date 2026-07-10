"""Implementation of ``conda broker enable``."""

from __future__ import annotations

from ... import Broker
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_enable(args, *, console=None) -> int:
    broker = Broker.current(ServicePaths.resolve(args.runtime_dir, args.log_dir))
    payload = broker.set_enabled(tuple(args.services), True)
    if args.start:
        payload = {**payload, **broker.start_services(tuple(args.services)).to_dict()}
    BrokerConsole(console).emit(args, payload)
    return 0

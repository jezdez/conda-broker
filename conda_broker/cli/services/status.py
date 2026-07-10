"""Implementation of ``conda broker status``."""

from __future__ import annotations

from ... import Broker
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_status(args, *, console=None) -> int:
    paths = ServicePaths.resolve(args.runtime_dir, args.log_dir)
    payload = Broker.current(paths).status(args.service).to_dict()
    BrokerConsole(console).emit(args, payload)
    return 0

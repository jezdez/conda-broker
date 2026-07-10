"""Implementation of ``conda broker list``."""

from __future__ import annotations

from ... import Broker
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_list(args, *, console=None) -> int:
    paths = ServicePaths.resolve(args.runtime_dir, args.log_dir)
    payload = Broker.current(paths).list_services()
    BrokerConsole(console).emit(args, payload)
    return 0

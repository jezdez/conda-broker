"""Implementation of ``conda broker doctor``."""

from __future__ import annotations

import os

from ... import Broker
from ...paths import ServicePaths
from ...registry import ServiceRegistry
from .common import BrokerConsole


def execute_doctor(args, *, console=None) -> int:
    paths = ServicePaths.resolve(args.runtime_dir, args.log_dir)
    paths.ensure()
    registry = ServiceRegistry.discover()
    checks = {
        "runtime_dir": str(paths.runtime_dir),
        "runtime_dir_writable": os.access(paths.runtime_dir, os.W_OK),
        "log_dir": str(paths.log_dir),
        "log_dir_writable": os.access(paths.log_dir, os.W_OK),
        "broker_running": Broker.current(paths).running(),
        "services_discovered": len(registry.all()),
        "provider_errors": list(registry.provider_errors),
    }
    payload = {"doctor": checks}
    BrokerConsole(console).emit(args, payload)
    return 0 if checks["runtime_dir_writable"] and checks["log_dir_writable"] else 1

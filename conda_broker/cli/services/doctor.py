"""Implementation of ``conda broker doctor``."""

from __future__ import annotations

import os

from ... import client
from ...registry import discover_services
from .common import emit_payload, paths_from_args


def execute_doctor(args, *, console=None) -> int:
    paths = paths_from_args(args)
    paths.ensure()
    registry = discover_services()
    checks = {
        "runtime_dir": str(paths.runtime_dir),
        "runtime_dir_writable": os.access(paths.runtime_dir, os.W_OK),
        "log_dir": str(paths.log_dir),
        "log_dir_writable": os.access(paths.log_dir, os.W_OK),
        "broker_running": client.broker_running(paths),
        "services_discovered": len(registry.all()),
    }
    payload = {"doctor": checks}
    emit_payload(args, payload, console=console)
    return 0 if checks["runtime_dir_writable"] and checks["log_dir_writable"] else 1

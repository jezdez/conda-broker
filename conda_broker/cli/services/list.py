"""Implementation of ``conda broker list``."""

from __future__ import annotations

from ... import Broker
from .common import emit_payload, paths_from_args


def execute_list(args, *, console=None) -> int:
    payload = Broker.current(paths_from_args(args)).list_services()
    emit_payload(args, payload, console=console)
    return 0

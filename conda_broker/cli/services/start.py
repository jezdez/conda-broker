"""Implementation of ``conda broker start``."""

from __future__ import annotations

from ... import Broker
from .common import emit_payload, paths_from_args


def execute_start(args, *, console=None) -> int:
    payload = (
        Broker.current(paths_from_args(args))
        .start_services(tuple(args.services), timeout_s=args.timeout)
        .to_dict()
    )
    emit_payload(args, payload, console=console)
    return 0

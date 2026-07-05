"""Implementation of ``conda broker stop``."""

from __future__ import annotations

from ... import Broker
from .common import emit_payload, paths_from_args


def execute_stop(args, *, console=None) -> int:
    broker = Broker.current(paths_from_args(args))
    if args.services:
        payload = broker.stop_services(tuple(args.services)).to_dict()
    else:
        payload = broker.stop()
    emit_payload(args, payload, console=console)
    return 0

"""Implementation of ``conda broker enable``."""

from __future__ import annotations

from ... import Broker
from .common import emit_payload, paths_from_args


def execute_enable(args, *, console=None) -> int:
    broker = Broker.current(paths_from_args(args))
    payload = broker.set_enabled(tuple(args.services), True)
    if args.start:
        payload = {**payload, **broker.start_services(tuple(args.services)).to_dict()}
    emit_payload(args, payload, console=console)
    return 0

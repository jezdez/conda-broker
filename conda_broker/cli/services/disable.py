"""Implementation of ``conda broker disable``."""

from __future__ import annotations

from ... import Broker
from .common import emit_payload, paths_from_args


def execute_disable(args, *, console=None) -> int:
    broker = Broker.current(paths_from_args(args))
    payload = broker.set_enabled(tuple(args.services), False)
    if args.stop:
        payload = {**payload, **broker.stop_services(tuple(args.services)).to_dict()}
    emit_payload(args, payload, console=console)
    return 0

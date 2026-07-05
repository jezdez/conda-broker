"""Implementation of ``conda broker restart``."""

from __future__ import annotations

from ... import Broker
from .common import emit_payload, paths_from_args


def execute_restart(args, *, console=None) -> int:
    broker = Broker.current(paths_from_args(args))
    if args.services:
        payload = broker.restart_services(
            tuple(args.services),
            timeout_s=args.timeout,
        ).to_dict()
    else:
        payload = {"broker": broker.restart(timeout_s=args.timeout).to_dict()}
    emit_payload(args, payload, console=console)
    return 0

"""Implementation of ``conda broker status``."""

from __future__ import annotations

from ... import Broker
from .common import emit_payload, paths_from_args


def execute_status(args, *, console=None) -> int:
    payload = Broker.current(paths_from_args(args)).status(args.service).to_dict()
    emit_payload(args, payload, console=console)
    return 0

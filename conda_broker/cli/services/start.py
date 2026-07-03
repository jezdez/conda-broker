"""Implementation of ``conda broker start``."""

from __future__ import annotations

from ... import client
from .common import emit_payload, paths_from_args


def execute_start(args, *, console=None) -> int:
    payload = client.start(
        tuple(args.services),
        paths=paths_from_args(args),
        timeout_s=args.timeout,
    )
    emit_payload(args, payload, console=console)
    return 0

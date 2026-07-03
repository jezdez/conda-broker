"""Implementation of ``conda broker restart``."""

from __future__ import annotations

from ... import client
from .common import emit_payload, paths_from_args


def execute_restart(args, *, console=None) -> int:
    payload = client.restart(
        tuple(args.services),
        paths=paths_from_args(args),
        timeout_s=args.timeout,
    )
    emit_payload(args, payload, console=console)
    return 0

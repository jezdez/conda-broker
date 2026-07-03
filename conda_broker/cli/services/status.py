"""Implementation of ``conda broker status``."""

from __future__ import annotations

from ... import client
from .common import emit_payload, paths_from_args


def execute_status(args, *, console=None) -> int:
    payload = client.status(args.service, paths=paths_from_args(args))
    emit_payload(args, payload, console=console)
    return 0

"""Implementation of ``conda broker enable``."""

from __future__ import annotations

from ... import client
from .common import emit_payload, paths_from_args


def execute_enable(args, *, console=None) -> int:
    paths = paths_from_args(args)
    payload = client.set_enabled(tuple(args.services), True, paths=paths)
    if args.start:
        payload = {**payload, **client.start(tuple(args.services), paths=paths)}
    emit_payload(args, payload, console=console)
    return 0

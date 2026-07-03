"""Implementation of ``conda broker disable``."""

from __future__ import annotations

from ... import client
from .common import emit_payload, paths_from_args


def execute_disable(args, *, console=None) -> int:
    paths = paths_from_args(args)
    payload = client.set_enabled(tuple(args.services), False, paths=paths)
    if args.stop:
        payload = {**payload, **client.stop(tuple(args.services), paths=paths)}
    emit_payload(args, payload, console=console)
    return 0

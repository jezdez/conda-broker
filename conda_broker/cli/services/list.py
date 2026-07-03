"""Implementation of ``conda broker list``."""

from __future__ import annotations

from ... import client
from .common import emit_payload, paths_from_args


def execute_list(args, *, console=None) -> int:
    payload = client.list_services(paths=paths_from_args(args))
    emit_payload(args, payload, console=console)
    return 0

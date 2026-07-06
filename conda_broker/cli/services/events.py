"""Implementation of ``conda broker events``."""

from __future__ import annotations

import json
import time

from ... import Broker
from .common import emit_payload, paths_from_args, print_event_line


def execute_events(args, *, console=None) -> int:
    broker = Broker.current(paths_from_args(args))
    if not args.follow:
        payload = broker.events(limit=args.lines)
        emit_payload(args, payload, console=console)
        return 0

    seen: set[str] = set()
    while True:
        payload = broker.events()
        events = payload.get("events", [])
        if isinstance(events, list):
            current: set[str] = set()
            for event in events:
                key = _event_key(event)
                current.add(key)
                if key in seen:
                    continue
                if args.json:
                    print(json.dumps(event, sort_keys=True))
                else:
                    print_event_line(event, console=console)
            seen = current
        time.sleep(1.0)


def _event_key(event: object) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"))

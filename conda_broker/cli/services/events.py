"""Implementation of ``conda broker events``."""

from __future__ import annotations

import json
import time

from ... import Broker
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_events(args, *, console=None) -> int:
    broker = Broker.current(ServicePaths.resolve(args.runtime_dir, args.log_dir))
    output = BrokerConsole(console)
    if not args.follow:
        payload = broker.events(limit=args.lines)
        output.emit(args, payload)
        return 0

    seen: set[str] = set()
    while True:
        payload = broker.events(limit=args.lines)
        events = payload.get("events", [])
        if isinstance(events, list):
            current: set[str] = set()
            for event in events:
                key = json.dumps(event, sort_keys=True, separators=(",", ":"))
                current.add(key)
                if key in seen:
                    continue
                if args.json:
                    output.json_line(event)
                else:
                    output.event(event)
            seen = current
        time.sleep(1.0)

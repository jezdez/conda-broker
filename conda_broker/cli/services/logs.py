"""Implementation of ``conda broker logs``."""

from __future__ import annotations

import json

from ...logs import LogManager
from .common import console_or_default, emit_json, paths_from_args


def execute_logs(args, *, console=None) -> int:
    logs = LogManager(paths_from_args(args))
    resolved_console = console_or_default(console)
    if args.follow:
        for line in logs.follow(args.service):
            if args.json:
                print(
                    json.dumps(
                        {"service": args.service, "line": line},
                        sort_keys=True,
                    )
                )
            else:
                resolved_console.print(line)
        return 0

    lines = logs.read_lines(
        args.service,
        lines=args.lines,
        include_previous=args.previous,
    )
    if args.json:
        emit_json({"service": args.service, "lines": lines}, console=console)
    else:
        for line in lines:
            resolved_console.print(line)
    return 0

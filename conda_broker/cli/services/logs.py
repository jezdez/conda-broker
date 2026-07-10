"""Implementation of ``conda broker logs``."""

from __future__ import annotations

from ...logs import LogManager
from ...paths import ServicePaths
from .common import BrokerConsole


def execute_logs(args, *, console=None) -> int:
    logs = LogManager(ServicePaths.resolve(args.runtime_dir, args.log_dir))
    output = BrokerConsole(console)
    if args.follow:
        for line in logs.follow(args.service):
            if args.json:
                output.json_line({"service": args.service, "line": line})
            else:
                output.line(line)
        return 0

    lines = logs.read_lines(
        args.service,
        lines=args.lines,
        include_previous=args.previous,
    )
    if args.json:
        output.json({"service": args.service, "lines": lines})
    else:
        for line in lines:
            output.line(line)
    return 0

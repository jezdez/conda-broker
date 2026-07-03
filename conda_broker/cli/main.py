"""Argparse configuration and dispatch for ``conda broker``."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from ..exceptions import CondaBrokerError

_COMMANDS = {
    "start": ("conda_broker.cli.services.start", "execute_start"),
    "stop": ("conda_broker.cli.services.stop", "execute_stop"),
    "restart": ("conda_broker.cli.services.restart", "execute_restart"),
    "status": ("conda_broker.cli.services.status", "execute_status"),
    "list": ("conda_broker.cli.services.list", "execute_list"),
    "logs": ("conda_broker.cli.services.logs", "execute_logs"),
    "enable": ("conda_broker.cli.services.enable", "execute_enable"),
    "disable": ("conda_broker.cli.services.disable", "execute_disable"),
    "events": ("conda_broker.cli.services.events", "execute_events"),
    "doctor": ("conda_broker.cli.services.doctor", "execute_doctor"),
}


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def _add_common_options(
    parser: argparse.ArgumentParser,
    *,
    suppress_defaults: bool = False,
) -> None:
    path_default = argparse.SUPPRESS if suppress_defaults else None
    json_default = argparse.SUPPRESS if suppress_defaults else False
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=path_default,
        help="Override the conda-broker runtime directory.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=path_default,
        help="Override the conda-broker log directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=json_default,
        help="Emit machine-readable JSON.",
    )


def generate_broker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cb",
        description="Manage long-running conda-adjacent services.",
    )
    configure_broker_parser(parser)
    return parser


def configure_broker_parser(parser: argparse.ArgumentParser) -> None:
    parser.description = "Manage long-running conda-adjacent services."
    _add_common_options(parser)
    sub = parser.add_subparsers(dest="subcmd")

    start_parser = sub.add_parser("start", help="Start the broker and services.")
    _add_common_options(start_parser, suppress_defaults=True)
    start_parser.add_argument("services", nargs="*", help="Services to start.")
    start_parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=5.0,
        help="Seconds to wait for broker startup.",
    )

    stop_parser = sub.add_parser("stop", help="Stop services or the broker.")
    _add_common_options(stop_parser, suppress_defaults=True)
    stop_parser.add_argument(
        "services",
        nargs="*",
        help="Services to stop. Omit to stop all services and the broker.",
    )

    restart_parser = sub.add_parser("restart", help="Restart services or the broker.")
    _add_common_options(restart_parser, suppress_defaults=True)
    restart_parser.add_argument("services", nargs="*", help="Services to restart.")
    restart_parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=5.0,
        help="Seconds to wait for broker startup.",
    )

    status_parser = sub.add_parser("status", help="Show broker and service status.")
    _add_common_options(status_parser, suppress_defaults=True)
    status_parser.add_argument("service", nargs="?", default=None)

    list_parser = sub.add_parser("list", help="List discovered services.")
    _add_common_options(list_parser, suppress_defaults=True)

    logs_parser = sub.add_parser("logs", help="Show service logs.")
    _add_common_options(logs_parser, suppress_defaults=True)
    logs_parser.add_argument("service")
    logs_parser.add_argument("--lines", type=_positive_int, default=50)
    logs_parser.add_argument("--previous", action="store_true", default=False)
    logs_parser.add_argument("--follow", "-f", action="store_true", default=False)

    enable_parser = sub.add_parser("enable", help="Enable services on broker start.")
    _add_common_options(enable_parser, suppress_defaults=True)
    enable_parser.add_argument("services", nargs="+")
    enable_parser.add_argument("--start", action="store_true", default=False)

    disable_parser = sub.add_parser("disable", help="Disable services on broker start.")
    _add_common_options(disable_parser, suppress_defaults=True)
    disable_parser.add_argument("services", nargs="+")
    disable_parser.add_argument("--stop", action="store_true", default=False)

    events_parser = sub.add_parser("events", help="Show broker events.")
    _add_common_options(events_parser, suppress_defaults=True)
    events_parser.add_argument("--lines", type=_positive_int, default=50)
    events_parser.add_argument("--follow", "-f", action="store_true", default=False)

    doctor_parser = sub.add_parser("doctor", help="Check conda-broker setup.")
    _add_common_options(doctor_parser, suppress_defaults=True)


def execute_broker(
    args: argparse.Namespace,
    *,
    parser: argparse.ArgumentParser | None = None,
    console: Console | None = None,
) -> int:
    if not getattr(args, "subcmd", None):
        if parser is not None:
            parser.print_help()
        return 0
    try:
        module_name, function_name = _COMMANDS[args.subcmd]
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        return int(function(args, console=console) or 0)
    except CondaBrokerError as exc:
        if getattr(args, "json", False):
            import json

            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        else:
            err_console = console or Console(stderr=True, highlight=False)
            err_console.print(f"[bold red]conda-broker:[/bold red] {escape(str(exc))}")
        return 1

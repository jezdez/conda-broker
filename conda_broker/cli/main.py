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
    "endpoint": ("conda_broker.cli.services.endpoint", "execute_endpoint"),
    "wait": ("conda_broker.cli.services.wait", "execute_wait"),
    "logs": ("conda_broker.cli.services.logs", "execute_logs"),
    "enable": ("conda_broker.cli.services.enable", "execute_enable"),
    "disable": ("conda_broker.cli.services.disable", "execute_disable"),
    "events": ("conda_broker.cli.services.events", "execute_events"),
    "doctor": ("conda_broker.cli.services.doctor", "execute_doctor"),
    "dev": ("conda_broker.cli.services.dev", "execute_dev"),
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

    start_parser = sub.add_parser(
        "start",
        help="Start the broker or selected services.",
    )
    _add_common_options(start_parser, suppress_defaults=True)
    start_parser.add_argument(
        "services",
        nargs="*",
        help=(
            "Services to start. Omit to start the broker and services enabled "
            "for broker startup."
        ),
    )
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

    endpoint_parser = sub.add_parser("endpoint", help="Show service endpoints.")
    _add_common_options(endpoint_parser, suppress_defaults=True)
    endpoint_parser.add_argument("service")
    endpoint_parser.add_argument("endpoint", nargs="?", default="default")

    wait_parser = sub.add_parser("wait", help="Wait for a service to become ready.")
    _add_common_options(wait_parser, suppress_defaults=True)
    wait_parser.add_argument("service")
    wait_parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=30.0,
        help="Seconds to wait for service readiness.",
    )
    wait_parser.add_argument(
        "--start",
        action="store_true",
        default=False,
        help="Start the broker and service before waiting.",
    )

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

    dev_parser = sub.add_parser(
        "dev",
        help="Validate and exercise provider service definitions.",
    )
    _add_common_options(dev_parser, suppress_defaults=True)
    dev_sub = dev_parser.add_subparsers(dest="devcmd", required=True)

    dev_validate = dev_sub.add_parser("validate", help="Validate one service spec.")
    _add_common_options(dev_validate, suppress_defaults=True)
    dev_validate.add_argument("service")

    dev_run = dev_sub.add_parser(
        "run",
        help="Run one service in an isolated workspace.",
    )
    _add_common_options(dev_run, suppress_defaults=True)
    dev_run.add_argument("service")
    dev_run.add_argument(
        "--duration",
        type=_positive_float,
        default=3.0,
        help="Seconds to observe the running service.",
    )
    dev_run.add_argument(
        "--timeout",
        type=_positive_float,
        default=5.0,
        help="Seconds to wait for each lifecycle transition.",
    )
    dev_run.add_argument(
        "--keep",
        action="store_true",
        default=False,
        help="Keep the temporary runtime/log workspace.",
    )

    dev_test = dev_sub.add_parser("test", help="Run a conformance scenario.")
    _add_common_options(dev_test, suppress_defaults=True)
    dev_test.add_argument("service")
    dev_test.add_argument(
        "--scenario",
        choices=["start-stop", "health", "crash"],
        default="start-stop",
        help="Scenario to run.",
    )
    dev_test.add_argument(
        "--timeout",
        type=_positive_float,
        default=5.0,
        help="Seconds to wait for each lifecycle transition.",
    )
    dev_test.add_argument(
        "--keep",
        action="store_true",
        default=False,
        help="Keep the temporary runtime/log workspace.",
    )

    dev_report = dev_sub.add_parser("report", help="Run the full conformance report.")
    _add_common_options(dev_report, suppress_defaults=True)
    dev_report.add_argument("service")
    dev_report.add_argument(
        "--timeout",
        type=_positive_float,
        default=5.0,
        help="Seconds to wait for each lifecycle transition.",
    )
    dev_report.add_argument(
        "--keep",
        action="store_true",
        default=False,
        help="Keep temporary runtime/log workspaces.",
    )


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

"""Argparse configuration and dispatch for ``conda broker``."""

from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from rich.console import Console

from ..exceptions import CondaBrokerError
from .services.common import BrokerConsole


@dataclass
class BrokerCLI:
    """Configure and dispatch the broker command line."""

    console: Console | None = None

    commands: ClassVar[dict[str, tuple[str, str]]] = {
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

    def positive_int(self, value: str) -> int:
        parsed = int(value)
        if parsed < 1:
            raise argparse.ArgumentTypeError("must be at least 1")
        return parsed

    def positive_float(self, value: str) -> float:
        parsed = float(value)
        if parsed <= 0:
            raise argparse.ArgumentTypeError("must be greater than 0")
        return parsed

    def add_common_options(
        self,
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

    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="cb",
            description="Manage long-running conda-adjacent services.",
        )
        self.configure(parser)
        return parser

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.description = "Manage long-running conda-adjacent services."
        self.add_common_options(parser)
        sub = parser.add_subparsers(dest="subcmd")

        start_parser = sub.add_parser(
            "start",
            help="Start the broker or selected services.",
        )
        self.add_common_options(start_parser, suppress_defaults=True)
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
            type=self.positive_float,
            default=5.0,
            help="Seconds to wait for broker startup.",
        )

        stop_parser = sub.add_parser("stop", help="Stop services or the broker.")
        self.add_common_options(stop_parser, suppress_defaults=True)
        stop_parser.add_argument(
            "services",
            nargs="*",
            help="Services to stop. Omit to stop all services and the broker.",
        )

        restart_parser = sub.add_parser(
            "restart", help="Restart services or the broker."
        )
        self.add_common_options(restart_parser, suppress_defaults=True)
        restart_parser.add_argument("services", nargs="*", help="Services to restart.")
        restart_parser.add_argument(
            "--timeout",
            type=self.positive_float,
            default=5.0,
            help="Seconds to wait for broker startup.",
        )

        status_parser = sub.add_parser("status", help="Show broker and service status.")
        self.add_common_options(status_parser, suppress_defaults=True)
        status_parser.add_argument("service", nargs="?", default=None)

        list_parser = sub.add_parser("list", help="List discovered services.")
        self.add_common_options(list_parser, suppress_defaults=True)

        endpoint_parser = sub.add_parser("endpoint", help="Show service endpoints.")
        self.add_common_options(endpoint_parser, suppress_defaults=True)
        endpoint_parser.add_argument("service")
        endpoint_parser.add_argument("endpoint", nargs="?", default="default")

        wait_parser = sub.add_parser("wait", help="Wait for a service to become ready.")
        self.add_common_options(wait_parser, suppress_defaults=True)
        wait_parser.add_argument("service")
        wait_parser.add_argument(
            "--timeout",
            type=self.positive_float,
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
        self.add_common_options(logs_parser, suppress_defaults=True)
        logs_parser.add_argument("service")
        logs_parser.add_argument("--lines", type=self.positive_int, default=50)
        logs_parser.add_argument("--previous", action="store_true", default=False)
        logs_parser.add_argument("--follow", "-f", action="store_true", default=False)

        enable_parser = sub.add_parser(
            "enable", help="Enable services on broker start."
        )
        self.add_common_options(enable_parser, suppress_defaults=True)
        enable_parser.add_argument("services", nargs="+")
        enable_parser.add_argument("--start", action="store_true", default=False)

        disable_parser = sub.add_parser(
            "disable", help="Disable services on broker start."
        )
        self.add_common_options(disable_parser, suppress_defaults=True)
        disable_parser.add_argument("services", nargs="+")
        disable_parser.add_argument("--stop", action="store_true", default=False)

        events_parser = sub.add_parser("events", help="Show broker events.")
        self.add_common_options(events_parser, suppress_defaults=True)
        events_parser.add_argument("--lines", type=self.positive_int, default=50)
        events_parser.add_argument("--follow", "-f", action="store_true", default=False)

        doctor_parser = sub.add_parser("doctor", help="Check conda-broker setup.")
        self.add_common_options(doctor_parser, suppress_defaults=True)

        dev_parser = sub.add_parser(
            "dev",
            help="Validate and exercise provider service definitions.",
        )
        self.add_common_options(dev_parser, suppress_defaults=True)
        dev_sub = dev_parser.add_subparsers(dest="devcmd", required=True)

        dev_validate = dev_sub.add_parser("validate", help="Validate one service spec.")
        self.add_common_options(dev_validate, suppress_defaults=True)
        dev_validate.add_argument("service")

        dev_run = dev_sub.add_parser(
            "run",
            help="Run one service in an isolated workspace.",
        )
        self.add_common_options(dev_run, suppress_defaults=True)
        dev_run.add_argument("service")
        dev_run.add_argument(
            "--duration",
            type=self.positive_float,
            default=3.0,
            help="Seconds to observe the running service.",
        )
        dev_run.add_argument(
            "--timeout",
            type=self.positive_float,
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
        self.add_common_options(dev_test, suppress_defaults=True)
        dev_test.add_argument("service")
        dev_test.add_argument(
            "--scenario",
            choices=["start-stop", "health", "crash"],
            default="start-stop",
            help="Scenario to run.",
        )
        dev_test.add_argument(
            "--timeout",
            type=self.positive_float,
            default=5.0,
            help="Seconds to wait for each lifecycle transition.",
        )
        dev_test.add_argument(
            "--keep",
            action="store_true",
            default=False,
            help="Keep the temporary runtime/log workspace.",
        )

        dev_report = dev_sub.add_parser(
            "report", help="Run the full conformance report."
        )
        self.add_common_options(dev_report, suppress_defaults=True)
        dev_report.add_argument("service")
        dev_report.add_argument(
            "--timeout",
            type=self.positive_float,
            default=5.0,
            help="Seconds to wait for each lifecycle transition.",
        )
        dev_report.add_argument(
            "--keep",
            action="store_true",
            default=False,
            help="Keep temporary runtime/log workspaces.",
        )

    def execute(
        self,
        args: argparse.Namespace,
        *,
        parser: argparse.ArgumentParser | None = None,
    ) -> int:
        if not getattr(args, "subcmd", None):
            if parser is not None:
                parser.print_help()
            return 0
        try:
            module_name, function_name = self.commands[args.subcmd]
            module = importlib.import_module(module_name)
            function = getattr(module, function_name)
            return int(function(args, console=self.console) or 0)
        except (CondaBrokerError, OSError) as exc:
            if getattr(args, "json", False):
                BrokerConsole(self.console).json_line({"ok": False, "error": str(exc)})
            else:
                error_console = self.console or Console(stderr=True, highlight=False)
                BrokerConsole(error_console).error(exc)
            return 1


def generate_broker_parser() -> argparse.ArgumentParser:
    """Build the standalone ``cb`` argument parser."""
    return BrokerCLI().parser()


def configure_broker_parser(parser: argparse.ArgumentParser) -> None:
    """Configure the parser supplied by conda's subcommand hook."""
    BrokerCLI().configure(parser)


def execute_broker(
    args: argparse.Namespace,
    *,
    parser: argparse.ArgumentParser | None = None,
    console: Console | None = None,
) -> int:
    """Dispatch a parsed broker command."""
    return BrokerCLI(console).execute(args, parser=parser)

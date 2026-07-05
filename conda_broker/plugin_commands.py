"""Argparse helpers for plugin-owned broker service commands."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape

from . import Broker
from .cli.services.common import console_or_default, emit_json, emit_payload
from .exceptions import CondaBrokerError
from .logs import LogManager
from .models import validate_service_name
from .paths import ServicePaths

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from rich.console import Console


_ACTION_ATTR = "_conda_broker_plugin_action"
_DEFAULT_COMMANDS = (
    "status",
    "start",
    "stop",
    "restart",
    "enable",
    "disable",
    "wait",
    "logs",
)


@dataclass(frozen=True, init=False)
class BrokerServiceCommands:
    """Install broker controls under another conda plugin's subcommand parser.

    The generated commands are scoped to the service names passed to the
    constructor. Positional service arguments use those names as argparse
    choices, and commands without explicit service arguments default to the
    same set.
    """

    services: tuple[str, ...]
    source: str
    commands: tuple[str, ...]

    def __init__(
        self,
        services: Sequence[str],
        *,
        source: str = "",
        commands: Sequence[str] = _DEFAULT_COMMANDS,
    ) -> None:
        normalized = tuple(dict.fromkeys(services))
        if not normalized:
            raise ValueError("BrokerServiceCommands requires at least one service")
        for service in normalized:
            validate_service_name(service)

        requested = tuple(dict.fromkeys(commands))
        unknown = sorted(set(requested) - set(_DEFAULT_COMMANDS))
        if unknown:
            raise ValueError(f"Unknown broker service commands: {', '.join(unknown)}")

        object.__setattr__(self, "services", normalized)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "commands", requested)

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        """Configure a parser whose subcommands are broker service commands."""
        subcommands = parser.add_subparsers(dest="broker_command")
        self.add_to_subparsers(subcommands)

    def add_to_subparsers(self, subcommands) -> None:
        """Add scoped broker commands to an existing subparser collection."""
        if "status" in self.commands:
            parser = subcommands.add_parser(
                "status",
                help="Show broker service status.",
            )
            self._add_common_options(parser)
            parser.add_argument(
                "services",
                nargs="*",
                choices=self.services,
                help="Services to inspect. Omit to inspect all plugin services.",
            )
            self._set_action(parser, "status")

        if "start" in self.commands:
            parser = subcommands.add_parser("start", help="Start broker services.")
            self._add_common_options(parser)
            parser.add_argument("services", nargs="*", choices=self.services)
            parser.add_argument(
                "--timeout",
                type=_positive_float,
                default=5.0,
                help="Seconds to wait for broker startup.",
            )
            self._set_action(parser, "start")

        if "stop" in self.commands:
            parser = subcommands.add_parser("stop", help="Stop broker services.")
            self._add_common_options(parser)
            parser.add_argument("services", nargs="*", choices=self.services)
            self._set_action(parser, "stop")

        if "restart" in self.commands:
            parser = subcommands.add_parser("restart", help="Restart broker services.")
            self._add_common_options(parser)
            parser.add_argument("services", nargs="*", choices=self.services)
            parser.add_argument(
                "--timeout",
                type=_positive_float,
                default=5.0,
                help="Seconds to wait for broker startup.",
            )
            self._set_action(parser, "restart")

        if "enable" in self.commands:
            parser = subcommands.add_parser(
                "enable",
                help="Enable broker services on broker start.",
            )
            self._add_common_options(parser)
            parser.add_argument("services", nargs="*", choices=self.services)
            parser.add_argument("--start", action="store_true", default=False)
            self._set_action(parser, "enable")

        if "disable" in self.commands:
            parser = subcommands.add_parser(
                "disable",
                help="Disable broker services on broker start.",
            )
            self._add_common_options(parser)
            parser.add_argument("services", nargs="*", choices=self.services)
            parser.add_argument("--stop", action="store_true", default=False)
            self._set_action(parser, "disable")

        if "wait" in self.commands:
            parser = subcommands.add_parser(
                "wait",
                help="Wait for a broker service to become ready.",
            )
            self._add_common_options(parser)
            parser.add_argument("service", nargs="?", choices=self.services)
            parser.add_argument(
                "--timeout",
                type=_positive_float,
                default=30.0,
                help="Seconds to wait for service readiness.",
            )
            parser.add_argument(
                "--start",
                action="store_true",
                default=False,
                help="Start the broker and service before waiting.",
            )
            self._set_action(parser, "wait")

        if "logs" in self.commands:
            parser = subcommands.add_parser("logs", help="Show broker service logs.")
            self._add_common_options(parser)
            parser.add_argument("service", nargs="?", choices=self.services)
            parser.add_argument("--lines", type=_positive_int, default=50)
            parser.add_argument("--previous", action="store_true", default=False)
            parser.add_argument("--follow", "-f", action="store_true", default=False)
            self._set_action(parser, "logs")

    def execute(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        """Execute a scoped broker service command."""
        action = getattr(args, _ACTION_ATTR, None)
        if action is None:
            raise SystemExit("Choose a broker service command.")

        try:
            return int(getattr(self, f"_execute_{action}")(args, console=console) or 0)
        except CondaBrokerError as exc:
            if getattr(args, "json", False):
                print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
            else:
                resolved_console = console_or_default(console)
                resolved_console.print(
                    f"[bold red]conda-broker:[/bold red] {escape(str(exc))}"
                )
            return 1

    def _execute_status(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        broker = Broker.current(_paths_from_args(args))
        services = self._selected_services(args)
        payload = self._status_payload(broker, services)
        emit_payload(args, payload, console=console)
        return 0

    def _execute_start(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        broker = Broker.current(_paths_from_args(args))
        payload = broker.start_services(
            self._selected_services(args),
            timeout_s=args.timeout,
        ).to_dict()
        emit_payload(args, payload, console=console)
        return 0

    def _execute_stop(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        broker = Broker.current(_paths_from_args(args))
        services = self._selected_services(args)
        if broker.running():
            payload = broker.stop_services(services).to_dict()
        else:
            payload = self._status_payload(broker, services)
        emit_payload(args, payload, console=console)
        return 0

    def _execute_restart(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        payload = (
            Broker.current(_paths_from_args(args))
            .restart_services(self._selected_services(args), timeout_s=args.timeout)
            .to_dict()
        )
        emit_payload(args, payload, console=console)
        return 0

    def _execute_enable(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        broker = Broker.current(_paths_from_args(args))
        services = self._selected_services(args)
        payload = broker.set_enabled(services, True)
        if args.start:
            payload = {**payload, **broker.start_services(services).to_dict()}
        emit_payload(args, payload, console=console)
        return 0

    def _execute_disable(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        broker = Broker.current(_paths_from_args(args))
        services = self._selected_services(args)
        payload = broker.set_enabled(services, False)
        if args.stop and broker.running():
            payload = {**payload, **broker.stop_services(services).to_dict()}
        emit_payload(args, payload, console=console)
        return 0

    def _execute_wait(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        service = self._selected_service(args)
        payload = (
            Broker.current(_paths_from_args(args))
            .service(service)
            .wait(timeout_s=args.timeout, start=args.start)
            .to_dict()
        )
        emit_payload(args, payload, console=console)
        services = payload.get("services")
        if not isinstance(services, list) or not services:
            return 1
        observed = services[0]
        return 0 if isinstance(observed, dict) and observed.get("ready") else 1

    def _execute_logs(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        service = self._selected_service(args)
        logs = LogManager(_paths_from_args(args))
        resolved_console = console_or_default(console)
        if args.follow:
            for line in logs.follow(service):
                if args.json:
                    print(
                        json.dumps(
                            {"service": service, "line": line},
                            sort_keys=True,
                        )
                    )
                else:
                    resolved_console.print(line)
            return 0

        lines = logs.read_lines(
            service,
            lines=args.lines,
            include_previous=args.previous,
        )
        if args.json:
            emit_json({"service": service, "lines": lines}, console=console)
        else:
            for line in lines:
                resolved_console.print(line)
        return 0

    def _status_payload(
        self,
        broker: Broker,
        services: tuple[str, ...],
    ) -> dict[str, Any]:
        payload = broker.status().to_dict()
        rows = [
            service
            for service in payload.get("services", [])
            if isinstance(service, dict) and service.get("name") in services
        ]
        found = {str(service.get("name")) for service in rows}
        for service in services:
            if service not in found:
                rows.append(self._missing_service_status(service))
        payload["services"] = rows
        return payload

    def _missing_service_status(self, service: str) -> dict[str, Any]:
        return {
            "name": service,
            "summary": "",
            "source": self.source,
            "runtime": "",
            "enabled": False,
            "state": "unknown-service",
            "running": False,
            "pid": None,
            "exit_code": None,
            "started_at": None,
            "restart_count": 0,
            "health": "unknown",
            "ready": False,
            "endpoints": {},
        }

    def _selected_services(self, args: argparse.Namespace) -> tuple[str, ...]:
        services = tuple(getattr(args, "services", ()) or self.services)
        self._validate_selected_services(services)
        return services

    def _selected_service(self, args: argparse.Namespace) -> str:
        service = getattr(args, "service", None)
        if service is None:
            if len(self.services) == 1:
                return self.services[0]
            raise CondaBrokerError("Choose one broker service.")
        self._validate_selected_services((service,))
        return str(service)

    def _validate_selected_services(self, services: tuple[str, ...]) -> None:
        invalid = sorted(set(services) - set(self.services))
        if invalid:
            raise CondaBrokerError(
                "Unknown broker service for this plugin: " + ", ".join(invalid)
            )

    def _add_common_options(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--runtime-dir",
            type=Path,
            default=None,
            help="Override the conda-broker runtime directory.",
        )
        parser.add_argument(
            "--log-dir",
            type=Path,
            default=None,
            help="Override the conda-broker log directory.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Emit machine-readable JSON.",
        )

    def _set_action(self, parser: argparse.ArgumentParser, action: str) -> None:
        parser.set_defaults(**{_ACTION_ATTR: action, "handler": self.execute})


def _paths_from_args(args: argparse.Namespace) -> ServicePaths:
    return ServicePaths.resolve(args.runtime_dir, args.log_dir)


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

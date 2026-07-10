"""Argparse helpers for plugin-owned broker service commands."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from . import Broker
from .cli.services.common import BrokerConsole
from .exceptions import CondaBrokerError
from .logs import LogManager
from .models import ServiceName
from .paths import ServicePaths

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from conda.plugins.types import CondaSubcommand
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
    choices, and commands without explicit service arguments default to the same
    set. The default parser shape mounts broker controls under ``services``,
    producing commands like ``conda my-plugin services status``.
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
            ServiceName(service)

        requested = tuple(dict.fromkeys(commands))
        unknown = sorted(set(requested) - set(_DEFAULT_COMMANDS))
        if unknown:
            raise ValueError(f"Unknown broker service commands: {', '.join(unknown)}")

        object.__setattr__(self, "services", normalized)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "commands", requested)

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        """Configure a parser with a ``services`` broker command group."""
        subcommands = parser.add_subparsers(dest="broker_command")
        self.add_group_to_subparsers(subcommands)

    def configure_commands_parser(self, parser: argparse.ArgumentParser) -> None:
        """Configure a parser whose subcommands are direct broker commands."""
        subcommands = parser.add_subparsers(dest="service_command")
        self.add_commands_to_subparsers(subcommands)

    def conda_subcommand(
        self,
        name: str,
        *,
        summary: str,
    ) -> CondaSubcommand:
        """Return a ``CondaSubcommand`` exposing this plugin's service group."""
        from conda.plugins.types import CondaSubcommand

        return CondaSubcommand(
            name=name,
            summary=summary,
            action=self.execute,
            configure_parser=self.configure_parser,
        )

    def add_commands_to_subparsers(self, subcommands) -> None:
        """Add direct broker commands to an existing subparser collection.

        Prefer ``configure_parser()`` or ``add_group_to_subparsers()`` for the
        standard ``services`` command group.
        """
        if "status" in self.commands:
            parser = subcommands.add_parser(
                "status",
                help="Show broker service status.",
            )
            self.add_common_options(parser)
            parser.add_argument(
                "services",
                nargs="*",
                type=self.service_argument,
                help="Services to inspect. Omit to inspect all plugin services.",
            )
            self.set_action(parser, "status")

        if "start" in self.commands:
            parser = subcommands.add_parser("start", help="Start broker services.")
            self.add_common_options(parser)
            parser.add_argument("services", nargs="*", type=self.service_argument)
            parser.add_argument(
                "--timeout",
                type=self.positive_float,
                default=5.0,
                help="Seconds to wait for broker startup.",
            )
            self.set_action(parser, "start")

        if "stop" in self.commands:
            parser = subcommands.add_parser("stop", help="Stop broker services.")
            self.add_common_options(parser)
            parser.add_argument("services", nargs="*", type=self.service_argument)
            self.set_action(parser, "stop")

        if "restart" in self.commands:
            parser = subcommands.add_parser("restart", help="Restart broker services.")
            self.add_common_options(parser)
            parser.add_argument("services", nargs="*", type=self.service_argument)
            parser.add_argument(
                "--timeout",
                type=self.positive_float,
                default=5.0,
                help="Seconds to wait for broker startup.",
            )
            self.set_action(parser, "restart")

        if "enable" in self.commands:
            parser = subcommands.add_parser(
                "enable",
                help="Enable broker services on broker start.",
            )
            self.add_common_options(parser)
            parser.add_argument("services", nargs="*", type=self.service_argument)
            parser.add_argument("--start", action="store_true", default=False)
            self.set_action(parser, "enable")

        if "disable" in self.commands:
            parser = subcommands.add_parser(
                "disable",
                help="Disable broker services on broker start.",
            )
            self.add_common_options(parser)
            parser.add_argument("services", nargs="*", type=self.service_argument)
            parser.add_argument("--stop", action="store_true", default=False)
            self.set_action(parser, "disable")

        if "wait" in self.commands:
            parser = subcommands.add_parser(
                "wait",
                help="Wait for a broker service to become ready.",
            )
            self.add_common_options(parser)
            parser.add_argument("service", nargs="?", type=self.service_argument)
            parser.add_argument(
                "--timeout",
                type=self.positive_float,
                default=30.0,
                help="Seconds to wait for service readiness.",
            )
            parser.add_argument(
                "--start",
                action="store_true",
                default=False,
                help="Start the broker and service before waiting.",
            )
            self.set_action(parser, "wait")

        if "logs" in self.commands:
            parser = subcommands.add_parser("logs", help="Show broker service logs.")
            self.add_common_options(parser)
            parser.add_argument("service", nargs="?", type=self.service_argument)
            parser.add_argument("--lines", type=self.positive_int, default=50)
            parser.add_argument("--previous", action="store_true", default=False)
            parser.add_argument("--follow", "-f", action="store_true", default=False)
            self.set_action(parser, "logs")

    def add_group_to_subparsers(
        self,
        subcommands,
        *,
        name: str = "services",
        help: str = "Manage broker services.",
        description: str | None = None,
    ) -> argparse.ArgumentParser:
        """Add broker commands under a named nested subcommand.

        This is the collision-free form for plugins that already own names such
        as ``status`` or ``start``. For example, mounting the default group
        creates commands like ``conda my-plugin services status``.
        """
        parser = subcommands.add_parser(name, help=help, description=description)
        parser.set_defaults(handler=self.execute)
        self.configure_commands_parser(parser)
        return parser

    def service_argument(self, value: str) -> str:
        if value not in self.services:
            choices = ", ".join(repr(service) for service in self.services)
            raise argparse.ArgumentTypeError(
                f"invalid choice: {value!r} (choose from {choices})"
            )
        return value

    def add_common_options(self, parser: argparse.ArgumentParser) -> None:
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

    def set_action(self, parser: argparse.ArgumentParser, action: str) -> None:
        parser.set_defaults(**{_ACTION_ATTR: action, "handler": self.execute})

    @staticmethod
    def positive_int(value: str) -> int:
        parsed = int(value)
        if parsed < 1:
            raise argparse.ArgumentTypeError("must be at least 1")
        return parsed

    @staticmethod
    def positive_float(value: str) -> float:
        parsed = float(value)
        if parsed <= 0:
            raise argparse.ArgumentTypeError("must be greater than 0")
        return parsed

    def execute(
        self,
        args: argparse.Namespace,
        *,
        console: Console | None = None,
    ) -> int:
        """Execute a scoped broker service command."""
        return _BrokerServiceCommand(self, args, BrokerConsole(console)).execute()


@dataclass
class _BrokerServiceCommand:
    """Execute broker commands within one plugin's service scope."""

    scope: BrokerServiceCommands
    args: argparse.Namespace
    output: BrokerConsole
    paths: ServicePaths = field(init=False)
    broker: Broker = field(init=False)

    def __post_init__(self) -> None:
        self.paths = ServicePaths.resolve(self.args.runtime_dir, self.args.log_dir)
        self.broker = Broker.current(self.paths)

    @property
    def services(self) -> tuple[str, ...]:
        return self.scope.services

    @property
    def source(self) -> str:
        return self.scope.source

    def execute(self) -> int:
        action = getattr(self.args, _ACTION_ATTR, None)
        handlers = {
            "status": self.status,
            "start": self.start,
            "stop": self.stop,
            "restart": self.restart,
            "enable": self.enable,
            "disable": self.disable,
            "wait": self.wait,
            "logs": self.logs,
        }
        handler = handlers.get(action)
        if handler is None:
            raise SystemExit("Choose a broker service command.")

        try:
            return int(handler() or 0)
        except (CondaBrokerError, OSError) as exc:
            if getattr(self.args, "json", False):
                self.output.json_line({"ok": False, "error": str(exc)})
            else:
                self.output.error(exc)
            return 1

    def status(self) -> int:
        services = self.selected_services()
        payload = self.status_payload(services)
        self.output.emit(self.args, payload)
        return 0

    def start(self) -> int:
        payload = self.broker.start_services(
            self.selected_services(),
            timeout_s=self.args.timeout,
        ).to_dict()
        self.output.emit(self.args, payload)
        return 0

    def stop(self) -> int:
        services = self.selected_services()
        if self.broker.running():
            payload = self.broker.stop_services(services).to_dict()
        else:
            payload = self.status_payload(services)
        self.output.emit(self.args, payload)
        return 0

    def restart(self) -> int:
        payload = self.broker.restart_services(
            self.selected_services(), timeout_s=self.args.timeout
        ).to_dict()
        self.output.emit(self.args, payload)
        return 0

    def enable(self) -> int:
        services = self.selected_services()
        payload = self.broker.set_enabled(services, True)
        if self.args.start:
            payload = {**payload, **self.broker.start_services(services).to_dict()}
        self.output.emit(self.args, payload)
        return 0

    def disable(self) -> int:
        services = self.selected_services()
        payload = self.broker.set_enabled(services, False)
        if self.args.stop and self.broker.running():
            payload = {**payload, **self.broker.stop_services(services).to_dict()}
        self.output.emit(self.args, payload)
        return 0

    def wait(self) -> int:
        service = self.selected_service()
        payload = (
            self.broker.service(service)
            .wait(timeout_s=self.args.timeout, start=self.args.start)
            .to_dict()
        )
        self.output.emit(self.args, payload)
        services = payload.get("services")
        if not isinstance(services, list) or not services:
            return 1
        observed = services[0]
        return 0 if isinstance(observed, dict) and observed.get("ready") else 1

    def logs(self) -> int:
        service = self.selected_service()
        logs = LogManager(self.paths)
        if self.args.follow:
            for line in logs.follow(service):
                if self.args.json:
                    self.output.json_line({"service": service, "line": line})
                else:
                    self.output.line(line)
            return 0

        lines = logs.read_lines(
            service,
            lines=self.args.lines,
            include_previous=self.args.previous,
        )
        if self.args.json:
            self.output.json({"service": service, "lines": lines})
        else:
            for line in lines:
                self.output.line(line)
        return 0

    def status_payload(
        self,
        services: tuple[str, ...],
    ) -> dict[str, Any]:
        payload = self.broker.status().to_dict()
        rows = [
            service
            for service in payload.get("services", [])
            if isinstance(service, dict) and service.get("name") in services
        ]
        found = {str(service.get("name")) for service in rows}
        for service in services:
            if service not in found:
                rows.append(self.missing_service_status(service))
        payload["services"] = rows
        return payload

    def missing_service_status(self, service: str) -> dict[str, Any]:
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

    def selected_services(self) -> tuple[str, ...]:
        services = tuple(getattr(self.args, "services", ()) or self.services)
        self.validate_selected_services(services)
        return services

    def selected_service(self) -> str:
        service = getattr(self.args, "service", None)
        if service is None:
            if len(self.services) == 1:
                return self.services[0]
            raise CondaBrokerError("Choose one broker service.")
        self.validate_selected_services((service,))
        return str(service)

    def validate_selected_services(self, services: tuple[str, ...]) -> None:
        invalid = sorted(set(services) - set(self.services))
        if invalid:
            raise CondaBrokerError(
                "Unknown broker service for this plugin: " + ", ".join(invalid)
            )

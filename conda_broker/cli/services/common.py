"""Rich output for broker CLI commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.table import Table

if TYPE_CHECKING:
    from argparse import Namespace
    from typing import Any


class BrokerConsole:
    """Render human and machine-readable broker command results."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(highlight=False)

    def emit(self, args: Namespace, payload: dict[str, Any]) -> None:
        if getattr(args, "json", False):
            self.json(payload)
        else:
            self.human(payload)

    def json(self, payload: object) -> None:
        self.console.print_json(
            json.dumps(payload, sort_keys=True),
            highlight=False,
        )

    def json_line(self, payload: object) -> None:
        self.console.print(
            json.dumps(payload, sort_keys=True),
            markup=False,
            highlight=False,
            soft_wrap=True,
        )

    def line(self, line: object) -> None:
        self.console.print(str(line), markup=False, highlight=False)

    def error(self, message: object) -> None:
        self.console.print(f"[bold red]conda-broker:[/bold red] {escape(str(message))}")

    def event(self, event: dict[str, Any]) -> None:
        timestamp = str(event.get("timestamp", ""))
        event_type = str(event.get("type", ""))
        service = event.get("service")
        service_text = f" {service}" if service else ""
        message = event.get("message") or ""
        self.console.print(
            escape(f"{timestamp} {event_type}{service_text} {message}".rstrip())
        )

    def human(self, payload: dict[str, Any]) -> None:
        broker = payload.get("broker")
        services = payload.get("services")
        if isinstance(services, list):
            if isinstance(broker, dict):
                self.broker_summary(broker)
            if any(
                isinstance(service, dict) and "state" not in service
                for service in services
            ):
                enabled = payload.get("enabled")
                self.service_catalog(
                    services,
                    enabled if isinstance(enabled, list) else [],
                )
            else:
                self.services(services)
            provider_errors = payload.get("provider_errors")
            if isinstance(provider_errors, list) and provider_errors:
                self.provider_errors(provider_errors)
            return

        if isinstance(broker, dict):
            self.broker(broker)

        enabled = payload.get("enabled")
        if isinstance(enabled, list):
            self.enabled(enabled)
            return

        events = payload.get("events")
        if isinstance(events, list):
            self.events(events)
            return

        endpoint = payload.get("endpoint")
        endpoints = payload.get("endpoints")
        if isinstance(endpoint, dict) or isinstance(endpoints, dict):
            self.endpoint(payload)
            return

        doctor = payload.get("doctor")
        if isinstance(doctor, dict):
            self.doctor(doctor)
            provider_errors = doctor.get("provider_errors")
            if isinstance(provider_errors, list) and provider_errors:
                self.provider_errors(provider_errors)
            return

        for key, value in payload.items():
            self.console.print(f"{escape(str(key))}: {escape(str(value))}")

    def broker(self, broker: dict[str, Any]) -> None:
        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Broker", style="bold")
        table.add_column("State")
        table.add_column("Started")
        state = "running" if broker.get("running") else "stopped"
        started = broker.get("started")
        started_text = "yes" if started else "no" if started is False else "-"
        table.add_row("conda-broker", state, started_text)
        self.console.print(table)

    def broker_summary(self, broker: dict[str, Any]) -> None:
        state = "running" if broker.get("running") else "stopped"
        started = broker.get("started")
        detail = "started yes" if started is True else "started no"
        if started is None:
            detail = "started -"
        self.console.print(f"[bold]conda-broker[/bold]: {escape(state)} ({detail})")

    def services(self, services: list[Any]) -> None:
        if not services:
            self.console.print("services: none")
            return
        endpoint_summaries = [
            self.endpoint_summary(service.get("endpoints"))
            if isinstance(service, dict)
            else "-"
            for service in services
        ]
        show_endpoint = any(summary != "-" for summary in endpoint_summaries)
        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Service", style="bold")
        table.add_column("State")
        table.add_column("Health")
        table.add_column("Ready")
        table.add_column("Enabled")
        table.add_column("PID", justify="right")
        table.add_column("Restarts", justify="right")
        if show_endpoint:
            table.add_column("Endpoint")
        table.add_column("Source")
        for service, endpoint_summary in zip(
            services, endpoint_summaries, strict=False
        ):
            if not isinstance(service, dict):
                continue
            row = [
                escape(str(service.get("name", ""))),
                escape(str(service.get("state", "unknown"))),
                escape(str(service.get("health", "unknown"))),
                "yes" if service.get("ready") else "no",
                "yes" if service.get("enabled") else "no",
                str(service.get("pid") or "-"),
                str(service.get("restart_count") or 0),
            ]
            if show_endpoint:
                row.append(escape(endpoint_summary))
            row.append(escape(str(service.get("source", ""))))
            table.add_row(*row)
        self.console.print(table)

    def service_catalog(self, services: list[Any], enabled: list[Any]) -> None:
        if not services:
            self.console.print("services: none")
            return
        enabled_names = {str(name) for name in enabled}
        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Service", style="bold")
        table.add_column("Runtime")
        table.add_column("Autostart")
        table.add_column("Enabled")
        table.add_column("Summary")
        table.add_column("Source")
        for service in services:
            if not isinstance(service, dict):
                continue
            name = str(service.get("name", ""))
            table.add_row(
                escape(name),
                escape(str(service.get("runtime", ""))),
                "yes" if service.get("start_policy") == "enabled" else "no",
                "yes" if name in enabled_names else "no",
                escape(str(service.get("summary", ""))),
                escape(str(service.get("source", ""))),
            )
        self.console.print(table)

    def enabled(self, enabled: list[Any]) -> None:
        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Enabled Services", style="bold")
        if not enabled:
            table.add_row("none")
        else:
            for service in enabled:
                table.add_row(escape(str(service)))
        self.console.print(table)

    def events(self, events: list[Any]) -> None:
        if not events:
            self.console.print("events: none")
            return
        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Time")
        table.add_column("Type", style="bold")
        table.add_column("Service")
        table.add_column("Message")
        for event in events:
            if not isinstance(event, dict):
                continue
            table.add_row(
                escape(str(event.get("timestamp", ""))),
                escape(str(event.get("type", ""))),
                escape(str(event.get("service") or "")),
                escape(str(event.get("message") or "")),
            )
        self.console.print(table)

    def doctor(self, doctor: dict[str, Any]) -> None:
        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Check", style="bold")
        table.add_column("Value")
        for key in sorted(doctor):
            value = doctor[key]
            if key == "provider_errors":
                continue
            value_text = (
                "yes" if value is True else "no" if value is False else str(value)
            )
            table.add_row(escape(str(key)), escape(value_text))
        self.console.print(table)

    def provider_errors(self, errors: list[Any]) -> None:
        table = Table(
            title="Provider errors",
            title_justify="left",
            show_edge=False,
            pad_edge=False,
        )
        table.add_column("Provider", style="bold")
        table.add_column("Phase")
        table.add_column("Error")
        for error in errors:
            if not isinstance(error, dict):
                continue
            table.add_row(
                escape(str(error.get("provider", ""))),
                escape(str(error.get("phase", ""))),
                escape(str(error.get("error", ""))),
            )
        self.console.print(table)

    def endpoint(self, payload: dict[str, Any]) -> None:
        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Service", style="bold")
        table.add_column("Endpoint")
        table.add_column("Protocol")
        table.add_column("Host")
        table.add_column("Port", justify="right")
        table.add_column("URL")
        endpoint = payload.get("endpoint")
        if isinstance(endpoint, dict):
            table.add_row(
                escape(str(payload.get("service", ""))),
                escape(str(endpoint.get("name", payload.get("endpoint_name", "")))),
                escape(str(endpoint.get("protocol", ""))),
                escape(str(endpoint.get("host", ""))),
                str(endpoint.get("port") or "-"),
                escape(str(endpoint.get("url") or "-")),
            )
        else:
            table.add_row(
                escape(str(payload.get("service", ""))),
                escape(str(payload.get("endpoint_name", "default"))),
                "-",
                "-",
                "-",
                "not available",
            )
        self.console.print(table)

    def endpoint_summary(self, endpoints: Any) -> str:
        if not isinstance(endpoints, dict) or not endpoints:
            return "-"
        default = endpoints.get("default")
        if isinstance(default, dict):
            return str(default.get("url") or default.get("name") or "default")
        return ", ".join(sorted(str(name) for name in endpoints))

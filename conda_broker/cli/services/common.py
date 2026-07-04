"""Shared CLI helpers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ...paths import ServicePaths

if TYPE_CHECKING:
    from typing import Any


def console_or_default(console: Console | None = None) -> Console:
    return console or Console(highlight=False)


def paths_from_args(args) -> ServicePaths:
    return ServicePaths.resolve(args.runtime_dir, args.log_dir)


def emit_json(payload: dict[str, Any], *, console: Console | None = None) -> None:
    console_or_default(console).print_json(json.dumps(payload, sort_keys=True))


def emit_payload(
    args,
    payload: dict[str, Any],
    *,
    console: Console | None = None,
) -> None:
    if getattr(args, "json", False):
        emit_json(payload, console=console)
    else:
        print_human(payload, console=console)


def print_human(payload: dict[str, Any], *, console: Console | None = None) -> None:
    resolved_console = console_or_default(console)
    broker = payload.get("broker")
    if isinstance(broker, dict):
        _print_broker(resolved_console, broker)

    services = payload.get("services")
    if isinstance(services, list):
        _print_services(resolved_console, services)
        return

    enabled = payload.get("enabled")
    if isinstance(enabled, list):
        _print_enabled(resolved_console, enabled)
        return

    events = payload.get("events")
    if isinstance(events, list):
        _print_events(resolved_console, events)
        return

    endpoint = payload.get("endpoint")
    endpoints = payload.get("endpoints")
    if isinstance(endpoint, dict) or isinstance(endpoints, dict):
        _print_endpoint(resolved_console, payload)
        return

    doctor = payload.get("doctor")
    if isinstance(doctor, dict):
        _print_doctor(resolved_console, doctor)
        return

    for key, value in payload.items():
        resolved_console.print(f"{escape(str(key))}: {escape(str(value))}")


def print_event_line(
    event: dict[str, Any],
    *,
    console: Console | None = None,
) -> None:
    timestamp = str(event.get("timestamp", ""))
    event_type = str(event.get("type", ""))
    service = event.get("service")
    service_text = f" {service}" if service else ""
    message = event.get("message") or ""
    console_or_default(console).print(
        escape(f"{timestamp} {event_type}{service_text} {message}".rstrip())
    )


def _print_broker(console: Console, broker: dict[str, Any]) -> None:
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("Broker", style="bold")
    table.add_column("State")
    table.add_column("Started")
    state = "running" if broker.get("running") else "stopped"
    started = broker.get("started")
    started_text = "yes" if started else "no" if started is False else "-"
    table.add_row("conda-broker", state, started_text)
    console.print(table)


def _print_services(console: Console, services: list[Any]) -> None:
    if not services:
        console.print("services: none")
        return
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("Service", style="bold")
    table.add_column("State")
    table.add_column("Health")
    table.add_column("Ready")
    table.add_column("Enabled")
    table.add_column("PID", justify="right")
    table.add_column("Restarts", justify="right")
    table.add_column("Endpoint")
    table.add_column("Source")
    for service in services:
        if not isinstance(service, dict):
            continue
        table.add_row(
            escape(str(service.get("name", ""))),
            escape(str(service.get("state", "unknown"))),
            escape(str(service.get("health", "unknown"))),
            "yes" if service.get("ready") else "no",
            "yes" if service.get("enabled") else "no",
            str(service.get("pid") or "-"),
            str(service.get("restart_count") or 0),
            escape(_endpoint_summary(service.get("endpoints"))),
            escape(str(service.get("source", ""))),
        )
    console.print(table)


def _print_enabled(console: Console, enabled: list[Any]) -> None:
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("Enabled Services", style="bold")
    if not enabled:
        table.add_row("none")
    else:
        for service in enabled:
            table.add_row(escape(str(service)))
    console.print(table)


def _print_events(console: Console, events: list[Any]) -> None:
    if not events:
        console.print("events: none")
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
    console.print(table)


def _print_doctor(console: Console, doctor: dict[str, Any]) -> None:
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("Check", style="bold")
    table.add_column("Value")
    for key in sorted(doctor):
        value = doctor[key]
        if isinstance(value, bool):
            value_text = "yes" if value else "no"
        else:
            value_text = str(value)
        table.add_row(escape(str(key)), escape(value_text))
    console.print(table)


def _print_endpoint(console: Console, payload: dict[str, Any]) -> None:
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
    console.print(table)


def _endpoint_summary(endpoints: Any) -> str:
    if not isinstance(endpoints, dict) or not endpoints:
        return "-"
    default = endpoints.get("default")
    if isinstance(default, dict):
        return str(default.get("url") or default.get("name") or "default")
    names = sorted(str(name) for name in endpoints)
    return ", ".join(names)

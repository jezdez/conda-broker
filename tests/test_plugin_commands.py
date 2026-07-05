"""Tests for plugin-owned broker service command helpers."""

from __future__ import annotations

import argparse
import json

import pytest

from conda_broker import Broker, StatusSnapshot
from conda_broker.models import ServiceStatus
from conda_broker.plugin_commands import BrokerServiceCommands


def test_plugin_service_commands_create_conda_subcommand() -> None:
    pytest.importorskip("conda")
    commands = BrokerServiceCommands(("plugin.api",))

    item = commands.conda_subcommand(
        "my-plugin",
        summary="Manage my-plugin services.",
    )

    assert item.name == "my-plugin"
    assert item.summary == "Manage my-plugin services."
    assert item.action == commands.execute
    assert item.configure_parser == commands.configure_parser


def test_plugin_service_commands_configure_parser() -> None:
    commands = BrokerServiceCommands(("plugin.api",))
    parser = argparse.ArgumentParser(prog="conda my-plugin")
    commands.configure_parser(parser)

    args = parser.parse_args(["services", "start", "--timeout", "1"])

    assert args.broker_command == "services"
    assert args.services == []
    assert args.timeout == 1
    assert args.handler == commands.execute

    with pytest.raises(SystemExit):
        parser.parse_args(["start"])


def test_plugin_service_commands_reject_foreign_service() -> None:
    commands = BrokerServiceCommands(("plugin.api",))
    parser = argparse.ArgumentParser(prog="conda my-plugin")
    commands.configure_parser(parser)

    with pytest.raises(SystemExit):
        parser.parse_args(["services", "status", "other.api"])


def test_plugin_service_commands_can_be_mounted_directly() -> None:
    commands = BrokerServiceCommands(("plugin.api",))
    parser = argparse.ArgumentParser(prog="conda my-plugin")
    subcommands = parser.add_subparsers(dest="command")
    run = subcommands.add_parser("run")
    run.set_defaults(handler=lambda args: 7)
    commands.add_commands_to_subparsers(subcommands)

    run_args = parser.parse_args(["run"])
    status_args = parser.parse_args(["status"])

    assert run_args.handler(run_args) == 7
    assert status_args.handler == commands.execute


def test_plugin_service_commands_configure_direct_commands_parser() -> None:
    commands = BrokerServiceCommands(("plugin.api",))
    parser = argparse.ArgumentParser(prog="conda my-plugin services")
    commands.configure_commands_parser(parser)

    args = parser.parse_args(["status"])

    assert args.service_command == "status"
    assert args.services == []
    assert args.handler == commands.execute


def test_plugin_service_commands_can_be_grouped_to_avoid_collisions() -> None:
    commands = BrokerServiceCommands(("plugin.api",))
    parser = argparse.ArgumentParser(prog="conda my-plugin")
    subcommands = parser.add_subparsers(dest="command")
    status = subcommands.add_parser("status")
    status.set_defaults(handler=lambda args: 3)
    commands.add_group_to_subparsers(subcommands)

    plugin_status_args = parser.parse_args(["status"])
    broker_status_args = parser.parse_args(["services", "status"])

    assert plugin_status_args.handler(plugin_status_args) == 3
    assert broker_status_args.command == "services"
    assert broker_status_args.services == []
    assert broker_status_args.handler == commands.execute


def test_grouped_plugin_service_commands_reject_foreign_service() -> None:
    commands = BrokerServiceCommands(("plugin.api",))
    parser = argparse.ArgumentParser(prog="conda my-plugin")
    subcommands = parser.add_subparsers(dest="command")
    commands.add_group_to_subparsers(subcommands, name="broker")

    with pytest.raises(SystemExit):
        parser.parse_args(["broker", "start", "other.api"])


def test_plugin_service_status_filters_to_plugin_services(
    monkeypatch,
    capsys,
) -> None:
    commands = BrokerServiceCommands(("plugin.api",), source="plugin")
    parser = argparse.ArgumentParser(prog="conda my-plugin")
    commands.configure_parser(parser)
    args = parser.parse_args(["services", "status", "--json"])

    def status(self: Broker, service: str | None = None) -> StatusSnapshot:
        return StatusSnapshot(
            services=(
                ServiceStatus(
                    name="plugin.api",
                    summary="Plugin API",
                    source="plugin",
                    runtime="process",
                    enabled=True,
                    state="running",
                    running=True,
                    ready=True,
                    health="healthy",
                ),
                ServiceStatus(
                    name="other.api",
                    summary="Other API",
                    source="other",
                    runtime="process",
                    enabled=True,
                    state="running",
                    running=True,
                    ready=True,
                    health="healthy",
                ),
            ),
        )

    monkeypatch.setattr(Broker, "status", status)

    assert commands.execute(args) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [service["name"] for service in payload["services"]] == ["plugin.api"]


def test_plugin_service_start_defaults_to_all_plugin_services(
    monkeypatch,
    capsys,
) -> None:
    commands = BrokerServiceCommands(("plugin.api", "plugin.worker"))
    parser = argparse.ArgumentParser(prog="conda my-plugin")
    commands.configure_parser(parser)
    args = parser.parse_args(["services", "start", "--json", "--timeout", "2"])
    calls: list[tuple[tuple[str, ...], float]] = []

    def start_services(
        self: Broker,
        services: str | list[str] | tuple[str, ...] = (),
        *,
        timeout_s: float = 5.0,
    ) -> StatusSnapshot:
        assert not isinstance(services, str)
        calls.append((tuple(services), timeout_s))
        return StatusSnapshot(
            services=(
                ServiceStatus(
                    name="plugin.api",
                    summary="Plugin API",
                    source="plugin",
                    runtime="process",
                    enabled=False,
                    state="running",
                    running=True,
                    ready=True,
                ),
            ),
        )

    monkeypatch.setattr(Broker, "start_services", start_services)

    assert commands.execute(args) == 0

    assert calls == [(("plugin.api", "plugin.worker"), 2.0)]
    payload = json.loads(capsys.readouterr().out)
    assert payload["services"][0]["name"] == "plugin.api"


def test_plugin_service_logs_defaults_for_single_service(
    service_paths,
    capsys,
) -> None:
    commands = BrokerServiceCommands(("plugin.api",))
    parser = argparse.ArgumentParser(prog="conda my-plugin")
    commands.configure_parser(parser)
    args = parser.parse_args(
        [
            "services",
            "logs",
            "--runtime-dir",
            str(service_paths.runtime_dir),
            "--log-dir",
            str(service_paths.log_dir),
            "--json",
        ]
    )
    service_paths.log_dir.mkdir(parents=True, exist_ok=True)
    (service_paths.log_dir / "plugin.api.log").write_text("ready\n", encoding="utf-8")

    assert commands.execute(args) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"service": "plugin.api", "lines": ["ready"]}

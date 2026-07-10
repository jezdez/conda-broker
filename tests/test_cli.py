"""Tests for parser configuration."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from rich.console import Console

from conda_broker import Broker, BrokerState, StatusSnapshot
from conda_broker.cli.main import execute_broker, generate_broker_parser
from conda_broker.cli.services.common import BrokerConsole
from conda_broker.models import ServiceStatus


def test_status_accepts_top_level_json() -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["--json", "status"])

    assert args.subcmd == "status"
    assert args.json is True


def test_status_accepts_subcommand_json() -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["status", "--json"])

    assert args.subcmd == "status"
    assert args.json is True


def test_start_parser_args() -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["start", "package-cache", "--timeout", "1"])

    assert args.subcmd == "start"
    assert args.services == ["package-cache"]
    assert args.timeout == 1


def test_start_without_services_starts_broker_only(
    monkeypatch,
    service_paths,
    capsys,
) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(
        [
            "start",
            "--json",
            "--runtime-dir",
            str(service_paths.runtime_dir),
            "--log-dir",
            str(service_paths.log_dir),
        ]
    )
    calls: list[tuple[str, float | str | None]] = []

    def start(self: Broker, *, timeout_s: float = 5.0) -> BrokerState:
        calls.append(("start", timeout_s))
        return BrokerState(running=True, started=True)

    def status(self: Broker, service: str | None = None) -> StatusSnapshot:
        calls.append(("status", service))
        return StatusSnapshot(
            services=(
                ServiceStatus(
                    name="package-cache",
                    summary="Package metadata cache",
                    source="tests",
                    runtime="process",
                    enabled=True,
                    state="starting",
                ),
            ),
        )

    def start_services(self: Broker, *args, **kwargs) -> StatusSnapshot:
        raise AssertionError("bare cb start must not start every discovered service")

    monkeypatch.setattr(Broker, "start", start)
    monkeypatch.setattr(Broker, "status", status)
    monkeypatch.setattr(Broker, "start_services", start_services)

    assert execute_broker(args, parser=parser) == 0

    payload = json.loads(capsys.readouterr().out)
    assert calls == [("start", 5.0), ("status", None)]
    assert payload["broker"] == {"running": True, "started": True}
    assert [service["name"] for service in payload["services"]] == ["package-cache"]


def test_dev_parser_args() -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(
        ["dev", "test", "package-cache", "--scenario", "crash", "--timeout", "2"]
    )

    assert args.subcmd == "dev"
    assert args.devcmd == "test"
    assert args.service == "package-cache"
    assert args.scenario == "crash"
    assert args.timeout == 2


def test_endpoint_parser_args() -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["endpoint", "package-cache", "api"])

    assert args.subcmd == "endpoint"
    assert args.service == "package-cache"
    assert args.endpoint == "api"


def test_wait_parser_args() -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["wait", "package-cache", "--timeout", "2", "--start"])

    assert args.subcmd == "wait"
    assert args.service == "package-cache"
    assert args.timeout == 2
    assert args.start is True


@pytest.mark.parametrize(
    "argv",
    [
        ["start", "--timeout", "0"],
        ["restart", "--timeout", "-1"],
        ["wait", "package-cache", "--timeout", "0"],
        ["logs", "package-cache", "--lines", "0"],
        ["events", "--lines", "-1"],
    ],
)
def test_parser_rejects_non_positive_numeric_options(argv: list[str]) -> None:
    parser = generate_broker_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(argv)


def test_no_subcommand_prints_help(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args([])

    assert execute_broker(args, parser=parser) == 0
    assert "conda-broker" in capsys.readouterr().out


def test_rich_status_output_uses_broker_term(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["status"])
    console = Console(file=None, force_terminal=False, color_system=None, width=120)

    BrokerConsole(console).emit(
        args,
        {
            "broker": {"running": False},
            "services": [
                {
                    "name": "package-cache",
                    "state": "stopped",
                    "health": "unknown",
                    "ready": False,
                    "enabled": True,
                    "pid": None,
                    "restart_count": 0,
                    "endpoints": {
                        "default": {
                            "name": "default",
                            "protocol": "http",
                            "host": "127.0.0.1",
                            "port": 8000,
                            "path": "/",
                            "url": "http://127.0.0.1:8000/",
                        }
                    },
                    "source": "tests",
                }
            ],
        },
    )

    output = capsys.readouterr().out
    assert "conda-broker" in output
    assert "package-cache" in output
    assert "http://127.0.0.1:8000/" in output


def test_rich_service_output_omits_empty_endpoint_column(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["start", "package-cache"])

    BrokerConsole().emit(
        args,
        {
            "broker": {"running": True, "started": True},
            "services": [
                {
                    "name": "package-cache",
                    "state": "starting",
                    "health": "unknown",
                    "ready": False,
                    "enabled": False,
                    "pid": 123,
                    "restart_count": 0,
                    "endpoints": {},
                    "source": "tests",
                }
            ],
        },
    )

    output = capsys.readouterr().out
    assert "conda-broker: running (started yes)" in output
    assert "Endpoint" not in output


def test_rich_list_output_uses_service_catalog_columns(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["list"])

    BrokerConsole().emit(
        args,
        {
            "services": [
                {
                    "name": "package-cache",
                    "summary": "Package metadata cache",
                    "source": "tests",
                    "runtime": "process",
                    "start_policy": "enabled",
                }
            ],
            "enabled": ["package-cache"],
            "provider_errors": [],
        },
    )

    output = capsys.readouterr().out
    assert "Autostart" in output
    assert "Summary" in output
    assert "Package metadata cache" in output
    assert "Health" not in output
    assert "PID" not in output


def test_rich_list_output_shows_escaped_provider_errors(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["list"])

    BrokerConsole().emit(
        args,
        {
            "services": [],
            "enabled": [],
            "provider_errors": [
                {
                    "provider": "broken[provider]",
                    "phase": "services",
                    "error": "bad [service]",
                }
            ],
        },
    )

    output = capsys.readouterr().out
    assert "Provider errors" in output
    assert "broken[provider]" in output
    assert "bad [service]" in output


def test_rich_endpoint_output(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["endpoint", "package-cache"])
    console = Console(file=None, force_terminal=False, color_system=None, width=120)

    BrokerConsole(console).emit(
        args,
        {
            "service": "package-cache",
            "endpoint_name": "default",
            "endpoint": {
                "name": "default",
                "protocol": "http",
                "host": "127.0.0.1",
                "port": 8000,
                "path": "/health",
                "url": "http://127.0.0.1:8000/health",
            },
            "endpoints": {},
        },
    )

    output = capsys.readouterr().out
    assert "package-cache" in output
    assert "http://127.0.0.1:8000/health" in output


def test_broker_console_json_is_parseable(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["status", "--json"])

    BrokerConsole().emit(args, {"broker": {"running": False}})

    assert json.loads(capsys.readouterr().out) == {"broker": {"running": False}}


def test_broker_console_json_has_no_terminal_color() -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["status", "--json"])
    output = StringIO()
    console = Console(file=output, force_terminal=True, color_system="standard")

    BrokerConsole(console).emit(args, {"broker": {"running": False}})

    assert "\x1b" not in output.getvalue()
    assert json.loads(output.getvalue()) == {"broker": {"running": False}}


def test_stop_is_idempotent_when_broker_is_not_running(
    monkeypatch,
    service_paths,
    capsys,
) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(
        [
            "stop",
            "--json",
            "--runtime-dir",
            str(service_paths.runtime_dir),
            "--log-dir",
            str(service_paths.log_dir),
        ]
    )
    monkeypatch.setattr(Broker, "running", lambda self: False)

    assert execute_broker(args, parser=parser) == 0

    assert json.loads(capsys.readouterr().out) == {
        "broker": {"running": False, "stopping": False}
    }


def test_cli_renders_filesystem_errors_without_traceback(
    monkeypatch,
    capsys,
) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["status"])

    def fail_status(self: Broker, service: str | None = None) -> StatusSnapshot:
        raise PermissionError("unsafe [runtime]")

    monkeypatch.setattr(Broker, "status", fail_status)

    assert execute_broker(args, parser=parser) == 1

    error = capsys.readouterr().err
    assert "unsafe [runtime]" in error
    assert "Traceback" not in error

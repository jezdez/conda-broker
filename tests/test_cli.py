"""Tests for parser configuration."""

from __future__ import annotations

import json

import pytest
from rich.console import Console

from conda_broker.cli.main import execute_broker, generate_broker_parser
from conda_broker.cli.services.common import emit_payload


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

    emit_payload(
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
        console=console,
    )

    output = capsys.readouterr().out
    assert "conda-broker" in output
    assert "package-cache" in output
    assert "http://127.0.0.1:8000/" in output


def test_rich_service_output_omits_empty_endpoint_column(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["start", "package-cache"])

    emit_payload(
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


def test_rich_endpoint_output(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["endpoint", "package-cache"])
    console = Console(file=None, force_terminal=False, color_system=None, width=120)

    emit_payload(
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
        console=console,
    )

    output = capsys.readouterr().out
    assert "package-cache" in output
    assert "http://127.0.0.1:8000/health" in output


def test_emit_payload_json_is_parseable(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["status", "--json"])

    emit_payload(args, {"broker": {"running": False}})

    assert json.loads(capsys.readouterr().out) == {"broker": {"running": False}}

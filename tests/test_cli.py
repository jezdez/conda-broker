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
    args = parser.parse_args(["start", "presto", "--timeout", "1"])

    assert args.subcmd == "start"
    assert args.services == ["presto"]
    assert args.timeout == 1


def test_dev_parser_args() -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(
        ["dev", "test", "presto", "--scenario", "crash", "--timeout", "2"]
    )

    assert args.subcmd == "dev"
    assert args.devcmd == "test"
    assert args.service == "presto"
    assert args.scenario == "crash"
    assert args.timeout == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["start", "--timeout", "0"],
        ["restart", "--timeout", "-1"],
        ["logs", "presto", "--lines", "0"],
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
                    "name": "presto",
                    "state": "stopped",
                    "health": "unknown",
                    "enabled": True,
                    "pid": None,
                    "restart_count": 0,
                    "source": "tests",
                }
            ],
        },
        console=console,
    )

    output = capsys.readouterr().out
    assert "conda-broker" in output
    assert "presto" in output


def test_emit_payload_json_is_parseable(capsys) -> None:
    parser = generate_broker_parser()
    args = parser.parse_args(["status", "--json"])

    emit_payload(args, {"broker": {"running": False}})

    assert json.loads(capsys.readouterr().out) == {"broker": {"running": False}}

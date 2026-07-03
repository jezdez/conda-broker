"""Tests for parser configuration."""

from __future__ import annotations

import json

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

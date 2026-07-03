"""Implementation of ``conda broker dev``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markup import escape
from rich.table import Table

from ... import conformance
from .common import console_or_default, emit_json

if TYPE_CHECKING:
    from typing import Any


def execute_dev(args, *, console=None) -> int:
    if args.devcmd == "validate":
        result = conformance.validate(args.service)
        payload = {"conformance": result.to_dict()}
    elif args.devcmd == "run":
        result = conformance.run(
            args.service,
            duration_s=args.duration,
            timeout_s=args.timeout,
            keep=args.keep,
        )
        payload = {"conformance": result.to_dict()}
    elif args.devcmd == "test":
        result = conformance.test(
            args.service,
            scenario=args.scenario,
            timeout_s=args.timeout,
            keep=args.keep,
        )
        payload = {"conformance": result.to_dict()}
    else:
        payload = conformance.report(
            args.service,
            timeout_s=args.timeout,
            keep=args.keep,
        )

    if getattr(args, "json", False):
        emit_json(payload, console=console)
    else:
        print_conformance(payload, console=console)
    return 0 if _payload_ok(payload) else 1


def print_conformance(
    payload: dict[str, Any],
    *,
    console=None,
) -> None:
    resolved_console = console_or_default(console)
    if "results" in payload:
        resolved_console.print(
            f"[bold]Conformance report:[/bold] {escape(str(payload['service']))}"
        )
        for result in payload["results"]:
            if isinstance(result, dict):
                _print_result(result, console=resolved_console)
        return
    result = payload.get("conformance")
    if isinstance(result, dict):
        _print_result(result, console=resolved_console)


def _payload_ok(payload: dict[str, Any]) -> bool:
    ok = payload.get("ok")
    if isinstance(ok, bool):
        return ok
    conformance = payload.get("conformance")
    if isinstance(conformance, dict):
        return conformance.get("ok") is True
    return False


def _print_result(result: dict[str, Any], *, console) -> None:
    title = result.get("command")
    scenario = result.get("scenario")
    suffix = f" / {scenario}" if scenario else ""
    state = "pass" if result.get("ok") else "fail"
    console.print(
        f"[bold]{escape(str(result.get('service')))}[/bold] "
        f"{escape(str(title))}{escape(suffix)}: {state}"
    )
    workspace = result.get("workspace")
    if workspace and result.get("kept"):
        console.print(f"workspace: {escape(str(workspace))}")

    checks = result.get("checks")
    if isinstance(checks, list):
        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Status", style="bold")
        table.add_column("Check")
        table.add_column("Message")
        for check in checks:
            if not isinstance(check, dict):
                continue
            table.add_row(
                escape(str(check.get("status", ""))),
                escape(str(check.get("name", ""))),
                escape(str(check.get("message", ""))),
            )
        console.print(table)

    status = result.get("status")
    if isinstance(status, dict):
        console.print(
            "state="
            f"{escape(str(status.get('state')))} "
            "health="
            f"{escape(str(status.get('health')))} "
            "restarts="
            f"{escape(str(status.get('restart_count')))}"
        )

"""Implementation of ``conda broker dev``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.table import Table

from ...conformance import ConformanceSuite
from .common import BrokerConsole

if TYPE_CHECKING:
    from typing import Any


def execute_dev(args, *, console=None) -> int:
    suite = ConformanceSuite()
    if args.devcmd == "validate":
        result = suite.validate(args.service)
        payload = {"conformance": result.to_dict()}
    elif args.devcmd == "run":
        result = suite.run(
            args.service,
            duration_s=args.duration,
            timeout_s=args.timeout,
            keep=args.keep,
        )
        payload = {"conformance": result.to_dict()}
    elif args.devcmd == "test":
        result = suite.test(
            args.service,
            scenario=args.scenario,
            timeout_s=args.timeout,
            keep=args.keep,
        )
        payload = {"conformance": result.to_dict()}
    else:
        payload = suite.report(
            args.service,
            timeout_s=args.timeout,
            keep=args.keep,
        )

    view = ConformanceView(BrokerConsole(console))
    if getattr(args, "json", False):
        view.output.json(payload)
    else:
        view.print(payload)
    return 0 if view.ok(payload) else 1


@dataclass
class ConformanceView:
    """Render conformance results on a broker console."""

    output: BrokerConsole

    def ok(self, payload: dict[str, Any]) -> bool:
        ok = payload.get("ok")
        if isinstance(ok, bool):
            return ok
        conformance = payload.get("conformance")
        return isinstance(conformance, dict) and conformance.get("ok") is True

    def print(self, payload: dict[str, Any]) -> None:
        if "results" in payload:
            self.output.console.print(
                f"[bold]Conformance report:[/bold] {escape(str(payload['service']))}"
            )
            for result in payload["results"]:
                if isinstance(result, dict):
                    self.result(result)
            return
        result = payload.get("conformance")
        if isinstance(result, dict):
            self.result(result)

    def result(self, result: dict[str, Any]) -> None:
        title = result.get("command")
        scenario = result.get("scenario")
        suffix = f" / {scenario}" if scenario else ""
        state = "pass" if result.get("ok") else "fail"
        self.output.console.print(
            f"[bold]{escape(str(result.get('service')))}[/bold] "
            f"{escape(str(title))}{escape(suffix)}: {state}"
        )
        workspace = result.get("workspace")
        if workspace and result.get("kept"):
            self.output.console.print(f"workspace: {escape(str(workspace))}")

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
            self.output.console.print(table)

        status = result.get("status")
        if isinstance(status, dict):
            self.output.console.print(
                "state="
                f"{escape(str(status.get('state')))} "
                "health="
                f"{escape(str(status.get('health')))} "
                "restarts="
                f"{escape(str(status.get('restart_count')))}"
            )

"""Validate demo tapes, fixture services, and documentation assets."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from importlib.metadata import distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "demos"
DOCS = ROOT / "docs"
FIXTURE = DEMOS / "fixtures" / "demo-provider"


def main() -> int:
    tapes = sorted(
        path for path in DEMOS.glob("*.tape") if not path.name.startswith("_")
    )
    docs = "\n".join(path.read_text(encoding="utf-8") for path in DOCS.rglob("*.md"))
    for tape in tapes:
        source = tape.read_text(encoding="utf-8")
        gif = tape.with_suffix(".gif")
        _require(
            "Source demos/_settings.tape" in source, f"{tape.name} has no settings"
        )
        _require('Type "clear"' not in source, f"{tape.name} hides a terminal clear")
        _require(".mp4" not in source, f"{tape.name} creates an unused MP4")
        _require("pixi shell-hook" not in source, f"{tape.name} embeds setup output")
        _require(
            "CONDA_BROKER_RUNTIME_DIR" not in source,
            f"{tape.name} embeds runtime setup",
        )
        _require(gif.exists() and gif.stat().st_size > 0, f"{gif.name} is missing")
        _require(gif.read_bytes().startswith(b"GIF8"), f"{gif.name} is not a GIF")
        _require(f"demos/{gif.name}" in docs, f"{gif.name} is not used by docs")

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(FIXTURE))
    entry_points = {
        entry_point.name: entry_point.value
        for distribution in distributions(path=[str(FIXTURE)])
        for entry_point in distribution.entry_points
        if entry_point.group == "conda_broker"
    }
    _require(
        entry_points == {"demo-provider": "demo_provider.broker"},
        "demo provider entry point metadata changed",
    )
    from demo_provider.broker import conda_broker_services
    from demo_provider.healthcheck import main as healthcheck

    services = list(conda_broker_services())
    _require(
        {service.name for service in services} == {"flaky", "healthcheck", "heartbeat"},
        "demo provider service set changed",
    )
    for service in services:
        process = service.merged_process()
        if len(process.argv) >= 3 and process.argv[1] == "-m":
            _require(
                importlib.util.find_spec(process.argv[2]) is not None,
                f"missing demo process module {process.argv[2]}",
            )

    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "health-state"
        previous = os.environ.get("CONDA_BROKER_DEMO_HEALTH_STATE")
        os.environ["CONDA_BROKER_DEMO_HEALTH_STATE"] = str(state)
        try:
            _require(healthcheck() == 1, "first demo health check must fail")
            _require(healthcheck() == 0, "second demo health check must pass")
        finally:
            if previous is None:
                os.environ.pop("CONDA_BROKER_DEMO_HEALTH_STATE", None)
            else:
                os.environ["CONDA_BROKER_DEMO_HEALTH_STATE"] = previous

    print(f"validated {len(tapes)} demo tapes")
    return 0


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


if __name__ == "__main__":
    raise SystemExit(main())

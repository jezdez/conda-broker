"""Prepare isolated workspaces and record the VHS demos."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "demos"
FIXTURE = DEMOS / "fixtures" / "demo-provider"
DEMO_ROOTS = {
    "health-check": "health",
    "json-status": "json",
    "logs-events": "logs",
    "provider-plugin": "provider",
    "quickstart": "quickstart",
    "restart-policy": "restart",
}


def main(name: str = "") -> int:
    names = [name] if name else list(DEMO_ROOTS)
    unknown = sorted(set(names) - set(DEMO_ROOTS))
    if unknown:
        raise SystemExit(f"Unknown demo: {unknown[0]}")

    for demo_name in names:
        _record(demo_name, FIXTURE)
    return 0


def _record(name: str, provider_path: Path) -> None:
    root = Path("/tmp") / f"conda-broker-demo-{DEMO_ROOTS[name]}"
    pythonpath = os.environ.get("PYTHONPATH")
    env = {
        **os.environ,
        "CONDA_BROKER_RUNTIME_DIR": str(root / "runtime"),
        "CONDA_BROKER_LOG_DIR": str(root / "logs"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": (
            str(provider_path)
            if not pythonpath
            else f"{provider_path}{os.pathsep}{pythonpath}"
        ),
    }
    if name == "health-check":
        env["CONDA_BROKER_DEMO_HEALTH_STATE"] = str(root / "health-state")
    elif name == "restart-policy":
        env["CONDA_BROKER_DEMO_FLAKY_STATE"] = str(root / "flaky-state")

    _stop_broker(env)
    shutil.rmtree(root, ignore_errors=True)
    try:
        subprocess.run(["vhs", str(DEMOS / f"{name}.tape")], env=env, check=True)
    finally:
        _stop_broker(env)


def _stop_broker(env: dict[str, str]) -> None:
    subprocess.run(
        [sys.executable, "-m", "conda_broker", "stop"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=10,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))

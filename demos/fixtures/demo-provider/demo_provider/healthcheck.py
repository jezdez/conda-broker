"""Health check that fails once, then succeeds."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    state_path = Path(
        os.environ.get(
            "CONDA_BROKER_DEMO_HEALTH_STATE",
            str(Path(tempfile.gettempdir()) / "conda-broker-demo-health-state"),
        )
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    checks = int(state_path.read_text(encoding="utf-8")) if state_path.exists() else 0
    state_path.write_text(str(checks + 1), encoding="utf-8")
    return 0 if checks else 1


if __name__ == "__main__":
    raise SystemExit(main())

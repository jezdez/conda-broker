"""Tests for demo sources and tracked render assets."""

from __future__ import annotations

import subprocess
import sys


def test_demo_assets_and_fixture_are_valid() -> None:
    result = subprocess.run(
        [sys.executable, "demos/check.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "validated 6 demo tapes" in result.stdout

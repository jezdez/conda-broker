"""Shared test fixtures for conda-broker."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conda_broker.paths import ServicePaths

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def service_paths(tmp_path: Path) -> ServicePaths:
    paths = ServicePaths(
        runtime_dir=tmp_path / "runtime" / "conda" / "broker",
        log_dir=tmp_path / "logs" / "conda" / "broker",
    )
    paths.ensure()
    return paths

"""Tests for conda plugin registration."""

from __future__ import annotations

import pytest


def test_conda_subcommand_registration() -> None:
    pytest.importorskip("conda")
    from conda_broker.plugin import conda_subcommands

    items = {item.name: item for item in conda_subcommands()}
    assert "broker" in items
    assert callable(items["broker"].action)
    assert callable(items["broker"].configure_parser)


def test_conda_settings_registration() -> None:
    pytest.importorskip("conda")
    from conda_broker.plugin import conda_settings

    items = {item.name: item for item in conda_settings()}
    assert "broker_runtime_dir" in items
    assert "broker_log_dir" in items


def test_provider_hookspec_uses_broker_name() -> None:
    from conda_broker import hookspec

    assert hasattr(hookspec, "conda_broker_services")

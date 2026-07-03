"""Conda plugin registration for conda-broker.

This module is imported on every conda invocation. Keep imports lazy so
normal conda commands do not pay for CLI, registry, or broker setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conda.plugins import hookimpl
from conda.plugins.types import CondaSubcommand

if TYPE_CHECKING:
    from collections.abc import Iterable


@hookimpl
def conda_subcommands() -> Iterable[CondaSubcommand]:
    from .cli import configure_broker_parser, execute_broker

    yield CondaSubcommand(
        name="broker",
        summary="Manage long-running conda-adjacent services.",
        action=execute_broker,
        configure_parser=configure_broker_parser,
    )


@hookimpl
def conda_settings():
    from conda.common.configuration import PrimitiveParameter
    from conda.plugins.types import CondaSetting

    yield CondaSetting(
        name="broker_runtime_dir",
        description="Runtime directory for conda-broker state.",
        parameter=PrimitiveParameter(None, element_type=str),
        aliases=("conda_broker_runtime_dir",),
    )
    yield CondaSetting(
        name="broker_log_dir",
        description="Log directory for conda-broker and service logs.",
        parameter=PrimitiveParameter(None, element_type=str),
        aliases=("conda_broker_log_dir",),
    )

"""Private pluggy hooks owned by conda-broker."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

PROJECT_NAME = "conda_broker"
ENTRY_POINT_GROUP = "conda_broker"

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .models import CondaService


hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


@hookspec
def conda_broker_services() -> Iterable[CondaService]:
    """Return brokered service definitions provided by this package."""
    raise NotImplementedError

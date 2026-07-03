"""Exceptions raised by conda-broker."""

from __future__ import annotations


class CondaBrokerError(Exception):
    """Base error for user-facing conda-broker failures."""


class ServiceValidationError(CondaBrokerError):
    """A service provider returned an invalid service definition."""


class DuplicateServiceError(ServiceValidationError):
    """Two providers registered the same service name."""


class UnknownServiceError(CondaBrokerError):
    """A requested service does not exist."""


class BrokerNotRunningError(CondaBrokerError):
    """The broker is not currently reachable."""


class IpcAuthError(CondaBrokerError):
    """The broker rejected an IPC request due to invalid authentication."""


class IpcError(CondaBrokerError):
    """The broker returned or caused an IPC error."""


class RuntimeUnavailableError(CondaBrokerError):
    """A requested runtime backend is not available."""

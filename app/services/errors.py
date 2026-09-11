"""Shared exceptions for the Stage 14 service boundaries.

Services raise domain errors; API routers map them to HTTP semantics.  This
keeps the service layer free of HTTP/status coupling.
"""


class ServiceError(Exception):
    """Base class for all service-layer errors."""


class NotFoundError(ServiceError):
    """Raised when a requested resource does not exist or is not visible."""


class OwnershipError(ServiceError):
    """Raised when a caller references a resource owned by another tenant."""


class SourceAttachError(ServiceError):
    """Raised when a source cannot be attached to a transformation."""


class OutputFormatError(ServiceError):
    """Raised when an output format is not part of the canonical vocabulary."""
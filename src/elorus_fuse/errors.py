"""Exceptions raised by the Elorus Fuse provider layer.

Every failure mode the client can hit is normalized into one of these, so callers
never see a ``requests`` exception, an HTTP status code, or a raw response body. Each
exception carries the structured detail a caller needs to build its own user-facing
message; none of them carry presentation copy, which belongs to the application.
"""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    # responses.py raises from this module, so the dependency must stay one-way:
    # errors.py knows MyDataError only as a type.
    from .responses import MyDataError


class ElorusFuseError(Exception):
    """Base class for every Elorus Fuse failure."""

    def __init__(self, message: str, *, messages: Sequence[str] = ()):
        super().__init__(message)
        #: Provider-supplied detail lines, if the failure came with any. Safe to show
        #: to an operator; already free of credentials and stack detail.
        self.messages = tuple(messages)


class ElorusFuseConfigurationError(ElorusFuseError):
    """The client was constructed with unusable configuration.

    Raised eagerly at construction rather than at request time, so a missing
    credential surfaces as a clear message instead of a confusing 401.
    """


class ElorusFuseTransportError(ElorusFuseError):
    """The request never produced a usable HTTP response.

    Covers timeouts, DNS and connection failures, and TLS errors. The invoice may or
    may not have reached Elorus, so callers must treat this as indeterminate rather
    than as a definite rejection.
    """


class ElorusFuseAuthenticationError(ElorusFuseError):
    """The API key was rejected (``401``) or lacks permission (``403``)."""

    def __init__(self, message: str, *, status_code: int, messages: Sequence[str] = ()):
        super().__init__(message, messages=messages)
        self.status_code = status_code


class ElorusFuseValidationError(ElorusFuseError):
    """Elorus rejected the payload before submitting it to myDATA (``400``).

    ``field_errors`` maps a payload field name to its messages. Errors that are not
    field-specific arrive under Elorus' ``integrity_errors`` key and are collected
    into ``messages`` instead.
    """

    def __init__(
        self,
        message: str,
        *,
        field_errors: Mapping[str, Sequence[str]] | None = None,
        messages: Sequence[str] = (),
    ):
        super().__init__(message, messages=messages)
        self.field_errors = dict(field_errors or {})


class ElorusFuseMyDataRejectionError(ElorusFuseError):
    """myDATA rejected the invoice and Elorus relayed the rejection (``400``).

    ``rejected_reason`` is Elorus' high-level code: ``1`` business validation errors,
    ``2`` invalid data submitted by the provider, ``3`` already signed.
    """

    def __init__(
        self,
        message: str,
        *,
        rejected_reason: int | None = None,
        errors: Sequence['MyDataError'] = (),
    ):
        super().__init__(message, messages=[str(error) for error in errors])
        self.rejected_reason = rejected_reason
        self.errors = tuple(errors)


class ElorusFuseProtocolError(ElorusFuseError):
    """Elorus answered, but not in a shape this client understands.

    An unexpected status code, a body that is not JSON, or a success payload missing
    the fields that identify the invoice.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = body

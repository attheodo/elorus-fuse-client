"""Normalized Elorus Fuse response types.

Elorus returns the full invoice back on every read, but callers only care about the
handful of fields that identify the document and record its myDATA fate. These types
narrow the payload to those fields while keeping the original body available for
audit.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .enums import MyDataStatus
from .errors import ElorusFuseProtocolError


@dataclass(frozen=True)
class MyDataError:
    """A single validation error as reported by myDATA."""

    #: ``None`` if the provider omitted the code.
    code: int | None
    message: str

    def __str__(self) -> str:
        return f'{self.code}: {self.message}'

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> 'MyDataError':
        return cls(code=payload.get('code'), message=payload.get('message', ''))


@dataclass(frozen=True)
class InvoiceResult:
    """An invoice as Elorus Fuse currently sees it.

    Returned both by invoice creation and by the lookup used to reconcile invoices
    accepted while myDATA was unreachable, since Elorus describes them identically.
    """

    uid: str
    mark: str = ''
    authentication_code: str = ''
    #: Elorus Fuse invoice overview page. Present as soon as the invoice exists.
    qr_url: str = ''
    #: IAPR verification page. Only once myDATA has acknowledged the invoice.
    mydata_qr_url: str = ''
    #: :class:`TransmissionFailure`; ``2`` when Elorus accepted the invoice but could
    #: not reach myDATA in real time. Left as a plain int: these codes are the
    #: provider's to choose, and an unrecognized one must not break parsing. Members
    #: of the enum compare equal to it, so it stays usable as one.
    transmission_failure: int | None = None
    #: :class:`RejectedReason`, likewise left uncoerced.
    rejected_reason: int | None = None
    mydata_errors: tuple[MyDataError, ...] = ()
    #: The untouched provider body, kept for audit and support.
    raw: Mapping[str, Any] = field(default_factory=dict)
    #: When Elorus created (issued) the invoice.
    created: datetime | None = None
    #: When Elorus submitted the invoice to myDATA.
    submitted: datetime | None = None

    @property
    def mydata_status(self) -> MyDataStatus:
        """Derive the submission status the way the Elorus docs describe it.

        An invoice that has a MARK has landed; one carrying a rejection reason or
        myDATA errors was refused; one with neither is still queued for submission.
        """
        if self.mark:
            return MyDataStatus.SUCCESS
        if self.rejected_reason or self.mydata_errors:
            return MyDataStatus.REJECTED
        return MyDataStatus.NOT_SUBMITTED

    @property
    def verification_url(self) -> str:
        """The best available page for verifying this invoice.

        Prefers the IAPR page, which is the authoritative one, and falls back to the
        Elorus overview page while myDATA has not answered. The Elorus page redirects
        to the IAPR one once the invoice is submitted, so the fallback stays correct
        even if it is never refreshed.
        """
        return self.mydata_qr_url or self.qr_url

    @classmethod
    def from_payload(cls, payload: Any) -> 'InvoiceResult':
        """Build a result from a provider body, rejecting anything unrecognizable."""
        if not isinstance(payload, Mapping):
            raise ElorusFuseProtocolError(
                'Expected a JSON object describing an invoice.', body=payload
            )

        uid = payload.get('uid')
        if not uid:
            raise ElorusFuseProtocolError(
                'Provider response is missing the invoice uid.', body=payload
            )

        mark = payload.get('mark')
        return cls(
            uid=str(uid),
            # Elorus types the MARK as an integer; it is an identifier, not a number.
            mark='' if mark in (None, '') else str(mark),
            authentication_code=payload.get('authentication_code') or '',
            qr_url=payload.get('qr_url') or '',
            mydata_qr_url=payload.get('mydata_qr_url') or '',
            transmission_failure=payload.get('transmission_failure'),
            rejected_reason=payload.get('rejected_reason'),
            mydata_errors=_mydata_errors(payload.get('mydata_errors')),
            raw=payload,
            created=_timestamp(payload.get('created')),
            submitted=_timestamp(payload.get('submitted')),
        )


def _timestamp(value: Any) -> datetime | None:
    """Ignore invalid or timezone-free timestamps in provider-owned data."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


def _mydata_errors(payload: Any) -> tuple[MyDataError, ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        return ()
    return tuple(
        MyDataError.from_payload(item) for item in payload if isinstance(item, Mapping)
    )

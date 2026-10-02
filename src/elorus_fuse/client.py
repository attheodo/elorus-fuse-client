"""HTTP client for the Elorus Fuse Developer API v1.0.

The client deliberately assumes nothing about the application embedding it: it takes
configuration as an argument, speaks in the dataclasses of this package, and turns
every failure into an ``ElorusFuseError``. Nothing above it needs to know that the
provider is reached over HTTP.

Provider documentation: https://developer.elorusfuse.gr/
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum, IntEnum
from functools import wraps
from types import TracebackType
from typing import Any, Concatenate, ParamSpec, Self, TypeVar, cast
from urllib.parse import urljoin

import requests

from .enums import (
    InvoiceSearchField,
    InvoiceSeriesFilter,
    InvoiceType,
    MyDataStatus,
    TransmissionFailure,
)
from .environments import Environment
from .errors import (
    ElorusFuseAmbiguousInvoiceError,
    ElorusFuseAuthenticationError,
    ElorusFuseConfigurationError,
    ElorusFuseError,
    ElorusFuseMyDataRejectionError,
    ElorusFuseProtocolError,
    ElorusFuseTransportError,
    ElorusFuseValidationError,
)
from .payloads import InvoiceDraft
from .responses import InvoicePage, InvoiceResult, MyDataError

INVOICE_PATH = '/v1_0/invoice/'
INVOICE_LIST_PATH = '/v1_0/invoice/list/'

#: Elorus returns non-field validation failures under this single key.
INTEGRITY_ERRORS_KEY = 'integrity_errors'

_P = ParamSpec('_P')
_R = TypeVar('_R')
_E = TypeVar('_E', bound=Enum)


def _credential_safe(
    method: Callable[Concatenate[Client, _P], _R],
) -> Callable[Concatenate[Client, _P], _R]:
    """Keep a provider echo of the API token out of public exception details."""

    @wraps(method)
    def wrapped(self: Client, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return method(self, *args, **kwargs)
        except ElorusFuseError as exc:
            _redact_error(exc, self._config.api_token)
            raise

    return cast('Callable[Concatenate[Client, _P], _R]', wrapped)


@dataclass(frozen=True)
class Config:
    """Everything the client needs to reach Elorus Fuse.

    ``environment`` is required and has no default: it decides whether a call issues a
    real invoice, so every caller states the intent rather than inheriting one. It
    also supplies the host, since sandbox and production are separate deployments on
    separate domains, each with its own API key.

    ``base_url`` overrides the host the environment would otherwise supply. It exists
    for a proxy or a host Elorus moves before this package catches up, and is not the
    way to pick an environment.
    """

    api_token: str = field(repr=False)
    environment: Environment
    base_url: str = ''
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not self.api_token:
            raise ElorusFuseConfigurationError(
                'No Elorus Fuse API token is configured.'
            )
        try:
            environment = Environment(self.environment)
        except ValueError as exc:
            valid = ', '.join(repr(member.value) for member in Environment)
            raise ElorusFuseConfigurationError(
                f'{self.environment!r} is not a valid Elorus Fuse environment; '
                f'expected one of {valid}.'
            ) from exc

        object.__setattr__(self, 'environment', environment)
        object.__setattr__(self, 'base_url', self.base_url or environment.base_url)


class Client:
    """Issues and reads invoices through Elorus Fuse.

    The client holds a connection pool. A long-lived process can keep one client for
    its lifetime; anything shorter-lived should release the pool when done, either by
    calling :meth:`close` or by using the client as a context manager::

        with Client(config) as client:
            result = client.create_invoice(draft)
    """

    def __init__(self, config: Config, session: requests.Session | None = None):
        self._config = config
        # Injectable so tests can substitute a transport, and so a caller can supply a
        # session with its own retry or pooling policy.
        self._session = session or requests.Session()
        # A session supplied by the caller is the caller's to close; it may be shared
        # with code this client knows nothing about.
        self._owns_session = self._session is not session

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the connection pool, if this client created it.

        A session passed to the constructor is left open. Safe to call more than once.
        """
        if self._owns_session:
            self._session.close()

    @_credential_safe
    def create_invoice(self, draft: InvoiceDraft) -> InvoiceResult:
        """Issue an invoice.

        A returned result means Elorus accepted and archived the document. That is not
        the same as myDATA having acknowledged it: check ``mydata_status``, because
        Elorus answers ``201`` even when it could not reach myDATA and will submit the
        invoice later.
        """
        payload = self._request('POST', INVOICE_PATH, json=draft.as_payload())
        return InvoiceResult.from_payload(payload)

    @_credential_safe
    def get_invoice(self, uid: str, *, organization_vat: str) -> InvoiceResult | None:
        """Look an invoice up by uid.

        Returns ``None`` if the provider has no such invoice.

        Used to reconcile invoices accepted while myDATA was unreachable. Unlike
        creation, this endpoint cannot infer the organization from a body, so the VAT
        number is passed as a header.
        """
        payload = self._request(
            'GET',
            INVOICE_LIST_PATH,
            params={'search': uid, 'search_fields': 'uid'},
            headers={'X-Organization': organization_vat},
        )
        results = payload.get('results') if isinstance(payload, Mapping) else None
        if not results:
            return None
        # `search` is a filter, not an exact lookup, so confirm the match rather than
        # trusting the first row.
        for item in results:
            if isinstance(item, Mapping) and item.get('uid') == uid:
                return InvoiceResult.from_payload(item)
        return None

    @_credential_safe
    def list_invoices(
        self,
        *,
        organization_vat: str,
        search: str | None = None,
        search_fields: Sequence[InvoiceSearchField | str] | str = (),
        period_from: date | None = None,
        period_to: date | None = None,
        invoice_type: InvoiceType | str | None = None,
        mydata_status: MyDataStatus | str | None = None,
        transmission_failure: TransmissionFailure | int | str | None = None,
        series: str | None = None,
        number: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        detailed_xml: bool | None = None,
    ) -> InvoicePage:
        """Return one filtered page from Elorus' invoice list endpoint.

        All documented query parameters are available. The provider defaults to 100
        rows per page and accepts at most 250. Enum fields also accept their raw wire
        values at runtime, consistent with the request models.
        """
        if not isinstance(organization_vat, str) or not organization_vat:
            raise ValueError('organization_vat must be non-empty.')
        if search is not None and not isinstance(search, str):
            raise ValueError('search must be a string.')
        if search_fields and search is None:
            raise ValueError('search_fields requires a search term.')
        if (period_from is None) != (period_to is None):
            raise ValueError('period_from and period_to must be provided together.')
        if period_from is not None and (
            not isinstance(period_from, date) or isinstance(period_from, datetime)
        ):
            raise ValueError('period_from must be a date.')
        if period_to is not None and (
            not isinstance(period_to, date) or isinstance(period_to, datetime)
        ):
            raise ValueError('period_to must be a date.')
        if series is not None and not isinstance(series, str):
            raise ValueError('series must be a string.')
        if number is not None and not isinstance(number, str):
            raise ValueError('number must be a string.')
        if page is not None and (
            isinstance(page, bool) or not isinstance(page, int) or page < 1
        ):
            raise ValueError('page must be a positive integer.')
        if page_size is not None and (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 250
        ):
            raise ValueError('page_size must be between 1 and 250.')
        if detailed_xml is not None and not isinstance(detailed_xml, bool):
            raise ValueError('detailed_xml must be a boolean.')

        if isinstance(search_fields, str):
            raw_search_fields = search_fields.strip()
            search_field_values: Sequence[InvoiceSearchField | str] = (
                tuple(part.strip() for part in raw_search_fields.split(','))
                if raw_search_fields
                else ()
            )
        else:
            search_field_values = search_fields
        normalized_search_fields = tuple(
            _query_enum(value, InvoiceSearchField, 'search_fields')
            for value in search_field_values
        )
        normalized_invoice_type = _optional_query_enum(
            invoice_type, InvoiceType, 'invoice_type'
        )
        normalized_status = _optional_query_enum(
            mydata_status, MyDataStatus, 'mydata_status'
        )
        normalized_failure = _optional_query_enum(
            transmission_failure, TransmissionFailure, 'transmission_failure'
        )

        params: dict[str, Any] = {}
        if search is not None:
            params['search'] = search
        if normalized_search_fields:
            params['search_fields'] = ','.join(
                field.value for field in normalized_search_fields
            )
        if period_from is not None and period_to is not None:
            params['period_from'] = period_from.isoformat()
            params['period_to'] = period_to.isoformat()
        if normalized_invoice_type is not None:
            params['invoice_type'] = normalized_invoice_type.value
        if normalized_status is not None:
            params['mydata_status'] = normalized_status.value
        if normalized_failure is not None:
            params['transmission_failure'] = str(normalized_failure.value)
        if series is not None:
            params['series'] = series
        if number is not None:
            params['number'] = number
        if page is not None:
            params['page'] = page
        if page_size is not None:
            params['page_size'] = page_size
        if detailed_xml is not None:
            params['detailed_xml'] = '1' if detailed_xml else '0'

        payload = self._request(
            'GET',
            INVOICE_LIST_PATH,
            params=params,
            headers={'X-Organization': organization_vat},
        )
        return InvoicePage.from_payload(payload)

    @_credential_safe
    def find_invoice(
        self, *, series: str, number: str, organization_vat: str
    ) -> InvoiceResult | None:
        """Require an exact series/number lookup to resolve to at most one invoice.

        Use this to investigate a create request whose outcome is unknown. A ``None``
        result does not prove that the invoice was never issued: the original request
        may still be in flight at Elorus. Do not use it as permission to create again.

        Raises :class:`ElorusFuseAmbiguousInvoiceError` when the provider reports
        multiple matches. Use :meth:`list_invoices` when multiple matches are useful.
        """
        if not number:
            raise ValueError('Invoice number must be non-empty.')
        series_filter = series if series else InvoiceSeriesFilter.NO_SEQUENCE
        page = self.list_invoices(
            organization_vat=organization_vat,
            series=series_filter,
            number=number,
            page_size=2,
        )
        for result in page.results:
            row = result.raw
            if row.get('series', '') != series or row.get('number') != number:
                raise ElorusFuseProtocolError(
                    'Elorus Fuse returned an invoice outside the requested series '
                    'and number.',
                    body=row,
                )
        if page.count and not page.results:
            raise ElorusFuseProtocolError(
                'Elorus Fuse returned an inconsistent invoice page.'
            )
        if page.count > 1:
            raise ElorusFuseAmbiguousInvoiceError(
                'More than one Elorus Fuse invoice matched the series and number.',
                count=page.count,
                matches=page.results,
            )
        if page.count != len(page.results):
            raise ElorusFuseProtocolError(
                'Elorus Fuse returned an inconsistent invoice page.'
            )
        return page.results[0] if page.results else None

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        url = urljoin(self._config.base_url, path)
        request_headers = {
            'Authorization': f'Token {self._config.api_token}',
            'Accept': 'application/json',
            **(headers or {}),
        }

        try:
            response = self._session.request(
                method,
                url,
                json=json,
                params=params,
                headers=request_headers,
                timeout=self._config.timeout_seconds,
            )
        except requests.Timeout:
            raise ElorusFuseTransportError(
                f'Elorus Fuse did not respond within '
                f'{self._config.timeout_seconds} seconds.'
            ) from None
        except requests.RequestException as exc:
            raise ElorusFuseTransportError(
                f'Could not reach Elorus Fuse: {exc.__class__.__name__}.'
            ) from None

        return self._handle(response)

    def _handle(self, response: requests.Response) -> Any:
        if response.status_code in (401, 403):
            raise ElorusFuseAuthenticationError(
                'Elorus Fuse rejected the API credentials.'
                if response.status_code == 401
                else 'The Elorus Fuse account is not allowed to perform this action.',
                status_code=response.status_code,
                messages=_detail_messages(_json_or_none(response)),
            )

        if response.status_code == 400:
            raise _bad_request_error(_json_or_none(response))

        if not response.ok:
            raise ElorusFuseProtocolError(
                f'Elorus Fuse returned an unexpected status {response.status_code}.',
                status_code=response.status_code,
                body=_json_or_none(response, fallback_to_text=True),
            )

        payload = _json_or_none(response)
        if payload is None:
            raise ElorusFuseProtocolError(
                'Elorus Fuse returned a response that is not valid JSON.',
                status_code=response.status_code,
                body=response.text[:500],
            )
        return payload


def _query_enum(value: Any, enum: type[_E], field_name: str) -> _E:
    """Normalize one list-filter code while accepting its raw wire value."""
    candidate = value
    if issubclass(enum, IntEnum) and isinstance(value, str):
        try:
            candidate = int(value)
        except ValueError:
            pass
    try:
        return enum(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{value!r} is not a valid {field_name}.') from exc


def _optional_query_enum(
    value: Any | None, enum: type[_E], field_name: str
) -> _E | None:
    return None if value is None else _query_enum(value, enum, field_name)


def _redact_error(exc: ElorusFuseError, token: str) -> None:
    """Remove a credential if the provider has echoed it in a failure response."""
    exc.args = _redact(exc.args, token)
    exc.messages = _redact(exc.messages, token)
    if isinstance(exc, ElorusFuseValidationError):
        exc.field_errors = _redact(exc.field_errors, token)
    if isinstance(exc, ElorusFuseMyDataRejectionError):
        exc.uid = _redact(exc.uid, token)
        exc.body = _redact(exc.body, token)
        exc.errors = tuple(
            replace(error, message=_redact(error.message, token))
            for error in exc.errors
        )
    if isinstance(exc, ElorusFuseProtocolError):
        exc.body = _redact(exc.body, token)
    if isinstance(exc, ElorusFuseAmbiguousInvoiceError):
        exc.matches = tuple(_redact_result(match, token) for match in exc.matches)


def _redact_result(result: InvoiceResult, token: str) -> InvoiceResult:
    return replace(
        result,
        uid=_redact(result.uid, token),
        mark=_redact(result.mark, token),
        authentication_code=_redact(result.authentication_code, token),
        qr_url=_redact(result.qr_url, token),
        mydata_qr_url=_redact(result.mydata_qr_url, token),
        mydata_xml=_redact(result.mydata_xml, token),
        mydata_errors=tuple(
            replace(error, message=_redact(error.message, token))
            for error in result.mydata_errors
        ),
        raw=_redact(result.raw, token),
    )


def _redact(value: Any, token: str) -> Any:
    """Copy nested JSON only where a secret actually appears."""
    if isinstance(value, str):
        return value.replace(token, '[REDACTED]') if token in value else value
    if isinstance(value, Mapping):
        pairs = [
            (_redact(key, token), _redact(item, token)) for key, item in value.items()
        ]
        if all(
            new_key is key and new_item is item
            for (key, item), (new_key, new_item) in zip(
                value.items(), pairs, strict=True
            )
        ):
            return value
        return dict(pairs)
    if isinstance(value, (list, tuple)):
        items = [_redact(item, token) for item in value]
        if all(
            original is cleaned for original, cleaned in zip(value, items, strict=True)
        ):
            return value
        return tuple(items) if isinstance(value, tuple) else items
    return value


def _json_or_none(
    response: requests.Response, *, fallback_to_text: bool = False
) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:500] if fallback_to_text else None


def _bad_request_error(body: Any) -> ElorusFuseError:
    """Turn one of Elorus' three ``400`` shapes into the matching exception."""
    if not isinstance(body, Mapping):
        return ElorusFuseProtocolError(
            'Elorus Fuse rejected the invoice without a readable explanation.',
            status_code=400,
            body=body,
        )

    if 'mydata_errors' in body or 'rejected_reason' in body:
        uid = body.get('uid')
        return ElorusFuseMyDataRejectionError(
            'myDATA rejected the invoice.',
            rejected_reason=body.get('rejected_reason'),
            errors=[
                MyDataError.from_payload(item)
                for item in body.get('mydata_errors') or []
                if isinstance(item, Mapping)
            ],
            uid=str(uid) if uid else '',
            body=body,
        )

    if INTEGRITY_ERRORS_KEY in body:
        return ElorusFuseValidationError(
            'Elorus Fuse rejected the invoice.',
            messages=_as_messages(body[INTEGRITY_ERRORS_KEY]),
        )

    field_errors = {field: _as_messages(value) for field, value in body.items()}
    return ElorusFuseValidationError(
        'Elorus Fuse rejected the invoice.',
        field_errors=field_errors,
        messages=[
            f'{field}: {message}'
            for field, messages in field_errors.items()
            for message in messages
        ],
    )


def _detail_messages(body: Any) -> list[str]:
    if isinstance(body, Mapping) and body.get('detail'):
        return [str(body['detail'])]
    return []


def _as_messages(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]

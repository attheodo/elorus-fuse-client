"""HTTP client for the Elorus Fuse Developer API v1.0.

The client deliberately assumes nothing about the application embedding it: it takes
configuration as an argument, speaks in the dataclasses of this package, and turns
every failure into an ``ElorusFuseError``. Nothing above it needs to know that the
provider is reached over HTTP.

Provider documentation: https://developer.elorusfuse.gr/
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self
from urllib.parse import urljoin

import requests

from .environments import Environment
from .errors import (
    ElorusFuseAuthenticationError,
    ElorusFuseConfigurationError,
    ElorusFuseError,
    ElorusFuseMyDataRejectionError,
    ElorusFuseProtocolError,
    ElorusFuseTransportError,
    ElorusFuseValidationError,
)
from .payloads import InvoiceDraft
from .responses import InvoiceResult, MyDataError

INVOICE_PATH = '/v1_0/invoice/'
INVOICE_LIST_PATH = '/v1_0/invoice/list/'

#: Elorus returns non-field validation failures under this single key.
INTEGRITY_ERRORS_KEY = 'integrity_errors'


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

    api_token: str
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

    def create_invoice(self, draft: InvoiceDraft) -> InvoiceResult:
        """Issue an invoice.

        A returned result means Elorus accepted and archived the document. That is not
        the same as myDATA having acknowledged it: check ``mydata_status``, because
        Elorus answers ``201`` even when it could not reach myDATA and will submit the
        invoice later.
        """
        payload = self._request('POST', INVOICE_PATH, json=draft.as_payload())
        return InvoiceResult.from_payload(payload)

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
        except requests.Timeout as exc:
            raise ElorusFuseTransportError(
                f'Elorus Fuse did not respond within '
                f'{self._config.timeout_seconds} seconds.'
            ) from exc
        except requests.RequestException as exc:
            raise ElorusFuseTransportError(
                f'Could not reach Elorus Fuse: {exc.__class__.__name__}.'
            ) from exc

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
        return ElorusFuseMyDataRejectionError(
            'myDATA rejected the invoice.',
            rejected_reason=body.get('rejected_reason'),
            errors=[
                MyDataError.from_payload(item)
                for item in body.get('mydata_errors') or []
                if isinstance(item, Mapping)
            ],
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

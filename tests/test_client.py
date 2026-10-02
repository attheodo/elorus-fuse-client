"""Tests for the Elorus Fuse HTTP client.

The transport is faked, so these never touch the network. Response bodies mirror the
shapes in Elorus' API documentation, including the undocumented 401.
"""

import json as jsonlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
import requests

from elorus_fuse import (
    Client,
    Config,
    ElorusFuseAuthenticationError,
    ElorusFuseConfigurationError,
    ElorusFuseDuplicateInvoiceError,
    ElorusFuseError,
    ElorusFuseMyDataRejectionError,
    ElorusFuseProtocolError,
    ElorusFuseTransportError,
    ElorusFuseValidationError,
    Environment,
    InvoiceDraft,
    MyDataStatus,
)

DraftFactory = Callable[..., InvoiceDraft]

ORGANIZATION_VAT = '123456789'


class FakeResponse:
    def __init__(self, status_code: int, body: Any = None, text: str | None = None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else jsonlib.dumps(body or {})

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        if self._body is None:
            raise ValueError('not json')
        return self._body


class FakeSession:
    """Records the requests it is given and replays a canned answer."""

    def __init__(
        self, response: FakeResponse | None = None, raises: Exception | None = None
    ):
        self._response = response
        self._raises = raises
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse | None:
        self.calls.append({'method': method, 'url': url, **kwargs})
        if self._raises:
            raise self._raises
        return self._response

    def close(self) -> None:
        self.closed = True


def build_client(
    response: FakeResponse | None = None,
    raises: Exception | None = None,
    **config_overrides: Any,
) -> tuple[Client, FakeSession]:
    session = FakeSession(response=response, raises=raises)
    config = Config(
        **{
            'api_token': 'secret-token',
            'environment': Environment.PRODUCTION,
            **config_overrides,
        }
    )
    return Client(config, session=session), session


ACCEPTED_BODY = {
    'uid': '3F2A9C1E7B4D',
    'mark': 400009999123456,
    'authentication_code': 'A1B2C3D4E5',
    'qr_url': 'https://app.elorusfuse.gr/i/3F2A9C1E7B4D',
    'mydata_qr_url': 'https://mydata.aade.gr/verify/3F2A9C1E7B4D',
    'transmission_failure': None,
}

DELAYED_BODY = {
    'uid': '9E8D7C6B5A43',
    'mark': None,
    'authentication_code': '',
    'qr_url': 'https://app.elorusfuse.gr/i/9E8D7C6B5A43',
    'mydata_qr_url': '',
    'transmission_failure': 2,
}


# Config


def test_missing_token_fails_at_construction() -> None:
    # Better a clear configuration error than a confusing 401 at issuance time.
    with pytest.raises(ElorusFuseConfigurationError):
        Config(api_token='', environment=Environment.SANDBOX)


def test_environment_is_required() -> None:
    # It decides whether a call issues a real invoice, so there is no default to
    # inherit by accident.
    with pytest.raises(TypeError):
        Config(api_token='t')


def test_each_environment_supplies_its_own_host() -> None:
    sandbox = Config(api_token='t', environment=Environment.SANDBOX)
    production = Config(api_token='t', environment=Environment.PRODUCTION)

    assert sandbox.base_url == 'https://api.fuse-staging.gr'
    assert production.base_url == 'https://api.elorusfuse.gr'


def test_the_two_environments_are_not_the_same_host() -> None:
    # A mismatched key then fails with a 401 instead of issuing a real invoice.
    assert Environment.SANDBOX.base_url != Environment.PRODUCTION.base_url


def test_environment_accepts_its_plain_string_value() -> None:
    config = Config(api_token='t', environment='sandbox')

    assert config.environment is Environment.SANDBOX
    assert config.base_url == 'https://api.fuse-staging.gr'


def test_an_unknown_environment_is_rejected() -> None:
    with pytest.raises(ElorusFuseConfigurationError, match='sandbox'):
        Config(api_token='t', environment='prod')


def test_base_url_overrides_the_environment_host() -> None:
    config = Config(
        api_token='t',
        environment=Environment.PRODUCTION,
        base_url='https://proxy.internal',
    )

    assert config.base_url == 'https://proxy.internal'


def test_config_repr_hides_the_api_token_without_changing_equality() -> None:
    config = Config(api_token='secret-token', environment=Environment.PRODUCTION)

    assert 'secret-token' not in repr(config)
    assert config == Config(
        api_token='secret-token', environment=Environment.PRODUCTION
    )
    assert config != Config(api_token='other-token', environment=Environment.PRODUCTION)


# Client lifecycle


def test_context_manager_closes_a_session_the_client_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[requests.Session] = []
    monkeypatch.setattr(requests.Session, 'close', lambda self: closed.append(self))

    with Client(Config(api_token='t', environment=Environment.SANDBOX)) as client:
        assert isinstance(client, Client)
        assert closed == []

    assert len(closed) == 1


def test_a_session_supplied_by_the_caller_is_left_open() -> None:
    # The caller owns it and may be sharing it with code the client knows nothing of.
    client, session = build_client()

    with client:
        pass
    client.close()

    assert session.closed is False


def test_close_is_safe_to_call_more_than_once() -> None:
    client = Client(Config(api_token='t', environment=Environment.SANDBOX))

    client.close()
    client.close()


# create_invoice: the request


def test_sends_token_auth_to_the_invoice_endpoint(make_draft: DraftFactory) -> None:
    client, session = build_client(FakeResponse(201, ACCEPTED_BODY))

    client.create_invoice(make_draft())

    (call,) = session.calls
    assert call['method'] == 'POST'
    assert call['url'] == 'https://api.elorusfuse.gr/v1_0/invoice/'
    assert call['headers']['Authorization'] == 'Token secret-token'
    assert call['json']['number'] == '141'


def test_sandbox_requests_go_to_the_staging_host(make_draft: DraftFactory) -> None:
    client, session = build_client(
        FakeResponse(201, ACCEPTED_BODY), environment=Environment.SANDBOX
    )

    client.create_invoice(make_draft())

    (call,) = session.calls
    assert call['url'] == 'https://api.fuse-staging.gr/v1_0/invoice/'


def test_honours_the_configured_timeout_and_base_url(
    make_draft: DraftFactory,
) -> None:
    client, session = build_client(
        FakeResponse(201, ACCEPTED_BODY),
        base_url='https://api.example.test',
        timeout_seconds=3.5,
    )

    client.create_invoice(make_draft())

    (call,) = session.calls
    assert call['url'] == 'https://api.example.test/v1_0/invoice/'
    assert call['timeout'] == 3.5


# create_invoice: success


def test_normalizes_an_accepted_invoice(make_draft: DraftFactory) -> None:
    client, _ = build_client(FakeResponse(201, ACCEPTED_BODY))

    result = client.create_invoice(make_draft())

    assert result.uid == '3F2A9C1E7B4D'
    assert result.mark == '400009999123456'
    assert result.authentication_code == 'A1B2C3D4E5'
    assert result.mydata_status == MyDataStatus.SUCCESS
    assert result.verification_url == 'https://mydata.aade.gr/verify/3F2A9C1E7B4D'
    assert result.raw == ACCEPTED_BODY


def test_delayed_submission_is_accepted_but_flagged_not_submitted(
    make_draft: DraftFactory,
) -> None:
    # Elorus answers 201 with transmission_failure=2 when myDATA is unreachable.
    client, _ = build_client(FakeResponse(201, DELAYED_BODY))

    result = client.create_invoice(make_draft())

    assert result.uid == '9E8D7C6B5A43'
    assert result.mark == ''
    assert result.authentication_code == ''
    assert result.transmission_failure == 2
    assert result.mydata_status == MyDataStatus.NOT_SUBMITTED


def test_verification_url_falls_back_to_the_elorus_page(
    make_draft: DraftFactory,
) -> None:
    # The IAPR page does not exist yet, so the QR must point somewhere valid.
    client, _ = build_client(FakeResponse(201, DELAYED_BODY))

    result = client.create_invoice(make_draft())

    assert result.verification_url == 'https://app.elorusfuse.gr/i/9E8D7C6B5A43'


# create_invoice: failure


def test_field_validation_errors_are_normalized(make_draft: DraftFactory) -> None:
    client, _ = build_client(
        FakeResponse(400, {'cp_vat_number': ['This field is required.']})
    )

    with pytest.raises(ElorusFuseValidationError) as excinfo:
        client.create_invoice(make_draft())

    assert excinfo.value.field_errors == {'cp_vat_number': ['This field is required.']}
    assert 'cp_vat_number: This field is required.' in excinfo.value.messages


def test_integrity_errors_are_normalized(make_draft: DraftFactory) -> None:
    client, _ = build_client(
        FakeResponse(400, {'integrity_errors': ['Totals do not add up.']})
    )

    with pytest.raises(ElorusFuseValidationError) as excinfo:
        client.create_invoice(make_draft())

    assert excinfo.value.messages == ('Totals do not add up.',)
    assert excinfo.value.field_errors == {}


def test_mydata_rejection_is_a_distinct_error(make_draft: DraftFactory) -> None:
    body = {
        'uid': 'REJECTED-UID',
        'rejected_reason': 1,
        'mydata_errors': [{'code': 217, 'message': 'Invalid counterpart VAT number'}],
    }
    client, _ = build_client(FakeResponse(400, body))

    with pytest.raises(ElorusFuseMyDataRejectionError) as excinfo:
        client.create_invoice(make_draft())

    assert excinfo.value.rejected_reason == 1
    assert excinfo.value.errors[0].code == 217
    assert excinfo.value.messages == ('217: Invalid counterpart VAT number',)
    assert excinfo.value.uid == 'REJECTED-UID'
    assert excinfo.value.body is body


def test_already_signed_rejection_without_error_list(
    make_draft: DraftFactory,
) -> None:
    client, _ = build_client(FakeResponse(400, {'rejected_reason': 3}))

    with pytest.raises(ElorusFuseMyDataRejectionError) as excinfo:
        client.create_invoice(make_draft())

    assert excinfo.value.rejected_reason == 3
    assert excinfo.value.uid == ''
    assert excinfo.value.body == {'rejected_reason': 3}


def test_unauthenticated_is_an_authentication_error(make_draft: DraftFactory) -> None:
    # The live API returns 401 here even though the spec documents only 403.
    client, _ = build_client(
        FakeResponse(401, {'detail': 'Authentication credentials were not provided.'})
    )

    with pytest.raises(ElorusFuseAuthenticationError) as excinfo:
        client.create_invoice(make_draft())

    assert excinfo.value.status_code == 401
    assert 'Authentication credentials were not provided.' in excinfo.value.messages


def test_forbidden_is_an_authentication_error(make_draft: DraftFactory) -> None:
    client, _ = build_client(FakeResponse(403, {'detail': 'Permission denied.'}))

    with pytest.raises(ElorusFuseAuthenticationError) as excinfo:
        client.create_invoice(make_draft())

    assert excinfo.value.status_code == 403


@pytest.mark.parametrize(
    'exception',
    [
        pytest.param(requests.Timeout('timed out'), id='timeout'),
        pytest.param(requests.ConnectionError('no route'), id='connection-failure'),
        # Any other requests exception must not escape the client either.
        pytest.param(requests.RequestException('boom'), id='any-requests-exception'),
    ],
)
def test_transport_failures_become_a_transport_error(
    make_draft: DraftFactory, exception: requests.RequestException
) -> None:
    client, _ = build_client(raises=exception)

    with pytest.raises(ElorusFuseTransportError):
        client.create_invoice(make_draft())


def test_server_error_becomes_a_protocol_error(make_draft: DraftFactory) -> None:
    client, _ = build_client(FakeResponse(500, None, text='<html>oops</html>'))

    with pytest.raises(ElorusFuseProtocolError) as excinfo:
        client.create_invoice(make_draft())

    assert excinfo.value.status_code == 500


def test_non_json_success_body_becomes_a_protocol_error(
    make_draft: DraftFactory,
) -> None:
    client, _ = build_client(FakeResponse(201, None, text='not json'))

    with pytest.raises(ElorusFuseProtocolError):
        client.create_invoice(make_draft())


def test_success_without_a_uid_becomes_a_protocol_error(
    make_draft: DraftFactory,
) -> None:
    # Without a uid the invoice could never be reconciled, so it is not usable.
    client, _ = build_client(FakeResponse(201, {'mark': 12345}))

    with pytest.raises(ElorusFuseProtocolError):
        client.create_invoice(make_draft())


def test_credentials_are_never_included_in_error_text(
    make_draft: DraftFactory,
) -> None:
    client, _ = build_client(FakeResponse(401, {'detail': 'nope'}))

    with pytest.raises(ElorusFuseAuthenticationError) as excinfo:
        client.create_invoice(make_draft())

    assert 'secret-token' not in str(excinfo.value)
    assert 'secret-token' not in ' '.join(excinfo.value.messages)


# get_invoice


def test_looks_the_invoice_up_by_uid_with_the_organization_header() -> None:
    client, session = build_client(
        FakeResponse(200, {'count': 1, 'results': [ACCEPTED_BODY]})
    )

    result = client.get_invoice('3F2A9C1E7B4D', organization_vat=ORGANIZATION_VAT)

    (call,) = session.calls
    assert call['method'] == 'GET'
    assert call['url'] == 'https://api.elorusfuse.gr/v1_0/invoice/list/'
    assert call['params']['search'] == '3F2A9C1E7B4D'
    assert call['headers']['X-Organization'] == ORGANIZATION_VAT
    assert result is not None
    assert result.mark == '400009999123456'


def test_returns_none_when_the_provider_has_no_such_invoice() -> None:
    client, _ = build_client(FakeResponse(200, {'count': 0, 'results': []}))

    assert client.get_invoice('missing', organization_vat=ORGANIZATION_VAT) is None


def test_ignores_rows_that_do_not_match_the_requested_uid() -> None:
    # `search` is a filter, not an exact lookup, so a near match is not a match.
    client, _ = build_client(
        FakeResponse(200, {'count': 1, 'results': [ACCEPTED_BODY]})
    )

    result = client.get_invoice('3F2A9C1E7B4D0000', organization_vat=ORGANIZATION_VAT)

    assert result is None


def test_surfaces_a_later_mydata_rejection() -> None:
    client, _ = build_client(
        FakeResponse(
            200,
            {
                'count': 1,
                'results': [
                    {
                        **DELAYED_BODY,
                        'rejected_reason': 1,
                        'mydata_errors': [{'code': 217, 'message': 'Bad VAT'}],
                    }
                ],
            },
        )
    )

    result = client.get_invoice('9E8D7C6B5A43', organization_vat=ORGANIZATION_VAT)

    assert result is not None
    assert result.mydata_status == MyDataStatus.REJECTED
    assert result.mydata_errors[0].message == 'Bad VAT'


def test_uid_refresh_can_remain_pending() -> None:
    client, _ = build_client(FakeResponse(200, {'count': 1, 'results': [DELAYED_BODY]}))

    result = client.get_invoice('9E8D7C6B5A43', organization_vat=ORGANIZATION_VAT)

    assert result is not None
    assert result.mydata_status is MyDataStatus.NOT_SUBMITTED


@pytest.mark.parametrize(
    ('created', 'submitted', 'expected_created', 'expected_submitted'),
    [
        (
            '2026-09-04T10:30:00+03:00',
            '2026-09-04T07:31:00Z',
            datetime(2026, 9, 4, 10, 30, tzinfo=timezone(timedelta(hours=3))),
            datetime(2026, 9, 4, 7, 31, tzinfo=UTC),
        ),
        ('2026-09-04T10:30:00', 'bad', None, None),
        (None, 123, None, None),
    ],
)
def test_timestamps_only_accept_aware_iso_datetimes(
    make_draft: DraftFactory,
    created: Any,
    submitted: Any,
    expected_created: datetime | None,
    expected_submitted: datetime | None,
) -> None:
    client, _ = build_client(
        FakeResponse(201, {**ACCEPTED_BODY, 'created': created, 'submitted': submitted})
    )
    result = client.create_invoice(make_draft())

    assert result.created == expected_created
    assert result.submitted == expected_submitted


# find_invoice: exact series/number reconciliation


def test_find_invoice_sends_exact_filters_and_organization_header() -> None:
    row = {**ACCEPTED_BODY, 'series': 'MV', 'number': '141'}
    client, session = build_client(FakeResponse(200, {'count': 1, 'results': [row]}))

    result = client.find_invoice(
        series='MV', number='141', organization_vat=ORGANIZATION_VAT
    )

    (call,) = session.calls
    assert call['method'] == 'GET'
    assert call['url'] == 'https://api.elorusfuse.gr/v1_0/invoice/list/'
    assert call['params'] == {'series': 'MV', 'number': '141'}
    assert call['headers']['X-Organization'] == ORGANIZATION_VAT
    assert result is not None
    assert result.uid == ACCEPTED_BODY['uid']


@pytest.mark.parametrize(
    ('series', 'wire_series', 'row_series'),
    [('', '-no-seq-', ''), ('', '-no-seq-', None), ('0', '0', '0')],
)
def test_find_invoice_preserves_special_series_values(
    series: str, wire_series: str, row_series: str | None
) -> None:
    row = {**ACCEPTED_BODY, 'number': '1'}
    if row_series is not None:
        row['series'] = row_series
    client, session = build_client(FakeResponse(200, {'count': 1, 'results': [row]}))

    result = client.find_invoice(
        series=series, number='1', organization_vat=ORGANIZATION_VAT
    )

    assert result is not None
    assert session.calls[0]['params']['series'] == wire_series


def test_find_invoice_rejects_empty_number_before_request() -> None:
    client, session = build_client()

    with pytest.raises(ValueError, match='number'):
        client.find_invoice(series='MV', number='', organization_vat=ORGANIZATION_VAT)

    assert session.calls == []


def test_find_invoice_returns_none_for_no_match() -> None:
    client, _ = build_client(FakeResponse(200, {'count': 0, 'results': []}))

    assert (
        client.find_invoice(series='MV', number='1', organization_vat=ORGANIZATION_VAT)
        is None
    )


@pytest.mark.parametrize(
    ('count', 'rows', 'expected_matches'),
    [
        (2, [{**ACCEPTED_BODY, 'series': 'MV', 'number': '1'}], 1),
        (
            2,
            [
                {**ACCEPTED_BODY, 'series': 'MV', 'number': '1'},
                {**DELAYED_BODY, 'series': 'MV', 'number': '1'},
            ],
            2,
        ),
    ],
)
def test_find_invoice_reports_duplicates_even_on_a_later_page(
    count: int, rows: list[dict[str, Any]], expected_matches: int
) -> None:
    client, _ = build_client(FakeResponse(200, {'count': count, 'results': rows}))

    with pytest.raises(ElorusFuseDuplicateInvoiceError) as excinfo:
        client.find_invoice(series='MV', number='1', organization_vat=ORGANIZATION_VAT)

    assert isinstance(excinfo.value, ElorusFuseProtocolError)
    assert excinfo.value.count == count
    assert len(excinfo.value.matches) == expected_matches
    assert {item.uid for item in excinfo.value.matches} == {row['uid'] for row in rows}


@pytest.mark.parametrize(
    'row',
    [
        {**ACCEPTED_BODY, 'series': 'OTHER', 'number': '1'},
        {**ACCEPTED_BODY, 'series': 'MV', 'number': '2'},
        {**ACCEPTED_BODY, 'number': '1'},
        'bad row',
    ],
)
def test_find_invoice_rejects_rows_outside_exact_filter(row: Any) -> None:
    client, _ = build_client(FakeResponse(200, {'count': 1, 'results': [row]}))

    with pytest.raises(ElorusFuseProtocolError):
        client.find_invoice(series='MV', number='1', organization_vat=ORGANIZATION_VAT)


@pytest.mark.parametrize(
    'body',
    [
        [],
        {'count': 0},
        {'count': 0, 'results': {}},
        {'results': []},
        {'count': True, 'results': []},
        {'count': 1, 'results': []},
    ],
)
def test_find_invoice_rejects_malformed_or_inconsistent_list(body: Any) -> None:
    client, _ = build_client(FakeResponse(200, body))

    with pytest.raises(ElorusFuseProtocolError):
        client.find_invoice(series='MV', number='1', organization_vat=ORGANIZATION_VAT)


@pytest.mark.parametrize(
    ('response', 'raises', 'error_type'),
    [
        (None, requests.Timeout('slow'), ElorusFuseTransportError),
        (
            FakeResponse(401, {'detail': 'bad token'}),
            None,
            ElorusFuseAuthenticationError,
        ),
        (
            FakeResponse(403, {'detail': 'forbidden'}),
            None,
            ElorusFuseAuthenticationError,
        ),
        (FakeResponse(500, {'detail': 'down'}), None, ElorusFuseProtocolError),
    ],
)
def test_find_invoice_uses_existing_transport_and_status_errors(
    response: FakeResponse | None,
    raises: Exception | None,
    error_type: type[Exception],
) -> None:
    client, _ = build_client(response, raises=raises)

    with pytest.raises(error_type):
        client.find_invoice(series='MV', number='1', organization_vat=ORGANIZATION_VAT)


@pytest.mark.parametrize(
    ('operation', 'response', 'raised'),
    [
        pytest.param('create', None, requests.Timeout('secret-token'), id='timeout'),
        pytest.param(
            'create', None, requests.ConnectionError('secret-token'), id='connection'
        ),
        pytest.param(
            'create', FakeResponse(401, {'detail': 'secret-token'}), None, id='401'
        ),
        pytest.param(
            'create', FakeResponse(403, {'detail': 'secret-token'}), None, id='403'
        ),
        pytest.param(
            'create',
            FakeResponse(400, {'secret-token': ['secret-token']}),
            None,
            id='400-field',
        ),
        pytest.param(
            'create',
            FakeResponse(400, {'integrity_errors': ['secret-token']}),
            None,
            id='400-integrity',
        ),
        pytest.param(
            'create',
            FakeResponse(
                400,
                {
                    'uid': 'secret-token',
                    'rejected_reason': 1,
                    'mydata_errors': [{'code': 123, 'message': 'secret-token'}],
                    'extra': {'nested': ['secret-token']},
                },
            ),
            None,
            id='400-mydata',
        ),
        pytest.param(
            'create', FakeResponse(400, ['secret-token']), None, id='400-malformed'
        ),
        pytest.param(
            'create',
            FakeResponse(500, {'detail': 'secret-token'}),
            None,
            id='unexpected-status',
        ),
        pytest.param(
            'create',
            FakeResponse(201, None, text='secret-token'),
            None,
            id='non-json',
        ),
        pytest.param(
            'create',
            FakeResponse(201, {'debug': 'secret-token'}),
            None,
            id='missing-uid',
        ),
        pytest.param(
            'find',
            FakeResponse(
                200,
                {
                    'count': 2,
                    'results': [
                        {
                            'uid': 'secret-token',
                            'series': 'MV',
                            'number': '1',
                            'debug': 'secret-token',
                        }
                    ],
                },
            ),
            None,
            id='duplicate',
        ),
        pytest.param(
            'find',
            FakeResponse(200, {'count': 1, 'results': 'secret-token'}),
            None,
            id='malformed-list',
        ),
    ],
)
def test_configured_token_is_absent_from_all_client_error_details(
    make_draft: DraftFactory,
    operation: str,
    response: FakeResponse | None,
    raised: Exception | None,
) -> None:
    client, _ = build_client(response, raises=raised)

    with pytest.raises(ElorusFuseError) as excinfo:
        if operation == 'find':
            client.find_invoice(
                series='MV', number='1', organization_vat=ORGANIZATION_VAT
            )
        else:
            client.create_invoice(make_draft())

    exc = excinfo.value
    assert 'secret-token' not in str(exc)
    assert 'secret-token' not in repr(exc)
    assert 'secret-token' not in repr(exc.messages)
    assert 'secret-token' not in repr(getattr(exc, 'body', None))
    assert 'secret-token' not in repr(vars(exc))

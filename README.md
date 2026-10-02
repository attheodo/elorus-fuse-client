# elorus-fuse-client

[![PyPI](https://img.shields.io/pypi/v/elorus-fuse-client)](https://pypi.org/project/elorus-fuse-client/)
[![Python versions](https://img.shields.io/pypi/pyversions/elorus-fuse-client)](https://pypi.org/project/elorus-fuse-client/)
[![License: MIT](https://img.shields.io/pypi/l/elorus-fuse-client)](https://github.com/attheodo/elorus-fuse-client/blob/main/LICENSE)

A typed Python client for the [Elorus Fuse Developer API](https://developer.elorusfuse.gr/),
for issuing Greek e-invoices through a certified provider and tracking what
[myDATA](https://www.aade.gr/mydata) does with them.

> **This is an unofficial client.** It is not affiliated with, endorsed by or supported
> by Elorus. For questions about your account or the API itself, contact Elorus.

## Status and scope

- **Two endpoints of nine.** The library can issue an invoice (`POST /v1_0/invoice/`)
  and list or filter issued invoices (`GET /v1_0/invoice/list/`).
  Invoice email, QR images, payment methods, cancellations and the rest are not
  implemented.
- **Pre-1.0.** The `0.x` series may make breaking changes between minor versions.
- **Tested against mocks only.** The request payload was checked field by field against
  Elorus' OpenAPI document, and every test fakes the HTTP transport. It has not yet
  issued an invoice with live Elorus credentials. Try it in the sandbox before using it
  in production.

## Installation

```console
pip install elorus-fuse-client
```

Requires Python 3.11 or newer. The only runtime dependency is
[`requests`](https://requests.readthedocs.io/). The package ships type hints
(PEP 561).

## Quickstart

```python
from datetime import date
from decimal import Decimal

from elorus_fuse import (
    Address,
    Client,
    Config,
    Environment,
    IncomeClassification,
    IncomeClassificationCategory,
    IncomeClassificationType,
    InvoiceDraft,
    InvoiceLine,
    InvoiceType,
    Party,
    VatCategory,
)

config = Config(api_token='your-sandbox-api-key', environment=Environment.SANDBOX)

draft = InvoiceDraft(
    issuer=Party(vat_number='123456789'),
    counterparty=Party(
        vat_number='987654321',
        name='ΠΑΡΑΔΕΙΓΜΑ ΑΕ',
        country='GR',
        address=Address(
            street='Εγνατία', number='15', postal_code='54625', city='Θεσσαλονίκη'
        ),
    ),
    invoice_type=InvoiceType.SERVICES_RENDERED,
    series='A',
    number='1',
    issue_date=date.today(),
    lines=[
        InvoiceLine(
            description='Consulting services',
            net_value=Decimal('100.00'),
            vat_category=VatCategory.VAT_24,
            vat_amount=Decimal('24.00'),
            income_classifications=[
                IncomeClassification(
                    category=IncomeClassificationCategory.SERVICES,
                    type=IncomeClassificationType.E3_561_001,
                    amount=Decimal('100.00'),
                )
            ],
        )
    ],
)

with Client(config) as client:
    result = client.create_invoice(draft)

print(result.uid, result.mydata_status, result.mark)
```

The issuer's VAT number identifies your Elorus organization, so it must belong to the
account the API key was issued for.

## A `201` does not guarantee a MARK

> **Elorus returns `201 Created` even when it could not reach myDATA.** In that case the
> invoice exists and is legally issued, but it has no MARK yet. Elorus submits it to
> myDATA later, on its own.

After issuing an invoice, check `result.mydata_status` before relying on the MARK:

```python
from elorus_fuse import MyDataStatus

match result.mydata_status:
    case MyDataStatus.SUCCESS:
        print('Registered with myDATA, MARK', result.mark)
    case MyDataStatus.NOT_SUBMITTED:
        # Issued, and queued at Elorus for myDATA. Do NOT issue it again.
        print('Issued; myDATA submission pending for', result.uid)
```

A caller that treats `NOT_SUBMITTED` as a failure and retries will **issue a duplicate
invoice**. A caller that stores the result without checking will end up with invoices
that have no MARK. Either way, the fix is the same:

1. Treat the invoice as issued, and store `result.uid`.
2. Accept that `mark` and `authentication_code` are empty for now.
3. Later, poll with `get_invoice` until the status settles:

```python
with Client(config) as client:
    latest = client.get_invoice(result.uid, organization_vat='123456789')

if latest is None:
    print('Elorus has no invoice with that uid')
elif latest.mydata_status is MyDataStatus.SUCCESS:
    print('Now registered, MARK', latest.mark)
elif latest.mydata_status is MyDataStatus.REJECTED:
    print('myDATA refused it:', [str(error) for error in latest.mydata_errors])
else:
    print('Still queued; try again later')
```

`organization_vat` is your issuer VAT number. The lookup endpoint cannot infer the
organization from a request body, so it has to be passed explicitly.

`list_invoices` exposes the complete documented JSON list endpoint. For example, this
fetches the second page of rejected service invoices from 2026 and asks Elorus to
include their detailed XML:

```python
from datetime import date

from elorus_fuse import InvoiceType, MyDataStatus

with Client(config) as client:
    page = client.list_invoices(
        organization_vat='123456789',
        period_from=date(2026, 1, 1),
        period_to=date(2026, 12, 31),
        invoice_type=InvoiceType.SERVICES_RENDERED,
        mydata_status=MyDataStatus.REJECTED,
        page=2,
        page_size=250,
        detailed_xml=True,
    )

print('total matches:', page.count, 'next:', page.next, 'previous:', page.previous)
for found in page.results:
    print(found.uid, found.created, found.mydata_xml)
```

Every documented filter is supported: `search`, `search_fields`, `period_from`,
`period_to`, `invoice_type`, `mydata_status`, `transmission_failure`, `series`,
`number`, `page`, `page_size` and `detailed_xml`. `search_fields` accepts
`InvoiceSearchField` members, raw values, or a comma-separated string; omitting it
makes Elorus search all searchable fields. Date bounds must be supplied together.
`page_size` may be at most 250.

`InvoicePage.count` is the total across every page, `results` contains the current
page, and `next`/`previous` carry Elorus' pagination URLs. The three special series
filters are available as `InvoiceSeriesFilter.NO_SEQUENCE`, `.ZERO` and
`.NO_SEQUENCE_OR_ZERO`. Each result retains the complete provider object in `.raw`,
including fields that the normalized response model does not expose directly.

If a create request timed out or a worker disappeared before saving its response,
`find_invoice` is a strict convenience for the exact series/number lookup. It returns
zero or one invoice. Multiple matches raise `ElorusFuseAmbiguousInvoiceError`, with
the provider's total in `.count` and up to two parsed rows in `.matches`. Applications
that expect multiple matches should call `list_invoices(series=..., number=...)`.

**A `None` result from `find_invoice` does not prove the invoice was never issued:**
the original create request may still be in flight. Do not treat `None` as permission
to create again. Use `get_invoice` when you already have a uid.

For display, `result.verification_url` gives the best available verification page. It
is the myDATA (IAPR) page once one exists, and before that the Elorus page, which
redirects to the IAPR one when myDATA answers.

In the sandbox, issue with `series='FAIL-500'` to simulate myDATA being unavailable
and exercise this path.

## Environments

Sandbox and production are separate deployments on separate hosts, each with its own
API key. `Config` has no default environment, because the choice decides whether a call
issues a real, legally binding invoice.

| `Environment` | Host |
| --- | --- |
| `Environment.SANDBOX` | `https://api.fuse-staging.gr` |
| `Environment.PRODUCTION` | `https://api.elorusfuse.gr` |

The sandbox host does not appear in Elorus' published API documentation. It was
confirmed with Elorus developer support.

A key used against the wrong environment fails with a `401` rather than issuing
anything. To route through a proxy, set `Config(base_url=...)`. This overrides the host
only, so still pass the environment you mean. The request timeout defaults to 15
seconds and can be changed with `Config(timeout_seconds=...)`.

## Building invoices

- **Totals are derived, not supplied.** `InvoiceDraft` computes the net, VAT and gross
  totals from its lines, so they can never disagree with the detail.
- **Amounts are rounded to cents**, half up, per line and before summing. Use
  `quantize_amount` to round figures you store yourself the same way.
- **VAT is supplied per line.** `VatCategory.VAT_24` is a myDATA code, not a rate, so
  compute `vat_amount` yourself.
- **VAT exemptions are optional.** Set `vat_exemption_category` to a
  `VatExemptionCategory` member or its numeric code. The client validates the code;
  Elorus validates whether it belongs with the invoice's VAT category.
- **Quantity and exchange rate use five decimal places.** Set `InvoiceLine.quantity`
  and `InvoiceDraft.exchange_rate` only when applicable. Both must be positive and
  are rounded half up; `quantize_rate` gives callers the exact value sent.
- **myDATA line comments are optional.** `line_comments_mydata` is sent only when
  nonempty and must be at most 150 characters. Truncate in the application if needed.
- **Retail invoices may omit the counterparty.** Pass `counterparty=None` explicitly
  to omit every `cp_*` field. The argument remains required, and Elorus decides which
  invoice types allow an absent counterparty.
- **Coded fields are validated when the draft is built.** Enum members and raw wire
  values (`vat_category=1`, `invoice_type='2.1'`) both work. An unknown code raises
  `ValueError` immediately, instead of coming back as a rejection of a real invoice.
- **Optional blocks are left out, not sent empty.** Add `payment_methods=[...]` with
  `PaymentMethod(type=PaymentMethodType.ON_CREDIT, amount=Decimal('124.00'))` and
  similar when you need them.

The myDATA vocabularies are exposed as enums: `InvoiceType`, `VatCategory`,
`VatExemptionCategory`, `PaymentMethodType`, `IncomeClassificationCategory`,
`IncomeClassificationType`, `TransmissionFailure`, `RejectedReason` and
`MyDataStatus`. The list endpoint also exposes `InvoiceSearchField` and
`InvoiceSeriesFilter`.

## Error handling

Every failure from the client is an `ElorusFuseError`, so callers never see a
`requests` exception, a raw status code or an unparsed body:

```text
ElorusFuseError
├── ElorusFuseConfigurationError    Config is unusable (missing token, unknown environment)
├── ElorusFuseTransportError        no usable response: timeout, DNS, connection, TLS
├── ElorusFuseAuthenticationError   401 bad or missing key, 403 not permitted (.status_code)
├── ElorusFuseValidationError       400, rejected by Elorus before myDATA (.field_errors)
├── ElorusFuseMyDataRejectionError  400, rejected by myDATA (.rejected_reason, .errors, .uid, .body)
├── ElorusFuseProtocolError         unexpected status, malformed body, success without a uid
└── ElorusFuseAmbiguousInvoiceError singular lookup has multiple matches (.count, .matches)
```

Every exception has a `.messages` tuple of provider-supplied detail lines, safe to show
to an operator. The configured API token is redacted if the provider echoes it in an
error. `ElorusFuseProtocolError` also carries `.status_code` and `.body` for diagnosis.
If a myDATA rejection names a held document, its `.uid` can be refreshed with
`get_invoice`; otherwise use `find_invoice` to investigate its series and number.

```python
from elorus_fuse import (
    ElorusFuseError,
    ElorusFuseMyDataRejectionError,
    ElorusFuseTransportError,
    ElorusFuseValidationError,
)

try:
    with Client(config) as client:
        result = client.create_invoice(draft)
except ElorusFuseValidationError as exc:
    print('Fix the draft:', exc.field_errors or exc.messages)
except ElorusFuseMyDataRejectionError as exc:
    print('myDATA refused it:', exc.rejected_reason, exc.messages)
except ElorusFuseTransportError:
    print('Unknown outcome: check Elorus before issuing again')
except ElorusFuseError as exc:
    print('Elorus Fuse call failed:', exc)
```

> **An `ElorusFuseTransportError` is indeterminate.** The request may or may not have
> reached Elorus, so the invoice may or may not exist. The library does not retry.
> Use `find_invoice` to investigate the intended series and number, and resolve any
> uncertainty before issuing again.

Invalid drafts are caught before any request is made. An unknown enum code or an
invoice with no lines raises a plain `ValueError` when the draft is constructed.

## Client lifecycle

`Client` holds a `requests.Session` connection pool. In a long-lived process, create one
client and reuse it. In scripts and short-lived jobs, use it as a context manager (as
above) or call `client.close()` when done.

To control retries, pooling or proxies at the transport level, pass your own session:
`Client(config, session=my_session)`. A session you supply is yours to close; the client
leaves it open.

## Further reading

- [Elorus Fuse Developer API](https://developer.elorusfuse.gr/) is the official
  documentation. It is incomplete in places: it omits the sandbox host and the `401`
  response described above.

## Development

```console
git clone https://github.com/attheodo/elorus-fuse-client.git
cd elorus-fuse-client
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

pytest            # tests: offline, all HTTP is faked
ruff check .      # lint
ruff format .     # format
mypy              # strict type-check of src/
```

## License

MIT. See [LICENSE](https://github.com/attheodo/elorus-fuse-client/blob/main/LICENSE). Release notes are in [CHANGELOG.md](https://github.com/attheodo/elorus-fuse-client/blob/main/CHANGELOG.md).

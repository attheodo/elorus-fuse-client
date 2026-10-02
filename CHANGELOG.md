# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the version is below 1.0.0, minor releases may contain breaking changes.

## [0.2.0] - 2026-10-02

### Added

- `VatExemptionCategory` with all 31 exemption codes, plus optional exemption,
  quantity and myDATA comment fields on `InvoiceLine`.
- Optional `InvoiceDraft.exchange_rate`, `InvoiceDraft.counterparty=None` for retail
  invoices, and `quantize_rate` for five-place half-up rounding.
- `Client.list_invoices`, covering every documented invoice-list filter and returning
  pagination metadata through `InvoicePage`.
- `InvoiceSearchField` and `InvoiceSeriesFilter` for the list endpoint's coded and
  special filter values, plus optional detailed XML on `InvoiceResult.mydata_xml`.
- `Client.find_invoice` as a strict reconciliation convenience, raising
  `ElorusFuseAmbiguousInvoiceError` when a singular lookup has multiple matches.
- `InvoiceResult.created` and `submitted` as timezone-aware datetimes when available.
- Rejection `uid` and response `body` on `ElorusFuseMyDataRejectionError`.

### Changed

- `Config` hides the API token from its representation. Client exceptions redact a
  token if the provider echoes it in an error response.

## [0.1.0] - 2026-09-18

First public release.

### Added

- `Client.create_invoice` issues an invoice through `POST /v1_0/invoice/`.
- `Client.get_invoice` looks an invoice up by uid through `GET /v1_0/invoice/list/`,
  matching the uid exactly because the provider's search is a filter.
- `Config`, with a required `Environment` (`SANDBOX` or `PRODUCTION`) that selects the
  host, plus `base_url` and `timeout_seconds` overrides.
- `Client.close()` and context-manager support. Only a session the client created is
  closed.
- Request models `InvoiceDraft`, `InvoiceLine`, `Party`, `Address`, `PaymentMethod` and
  `IncomeClassification`. Totals are derived from the lines, and amounts are rounded
  to cents half up by `quantize_amount`.
- myDATA vocabularies as enums: `InvoiceType`, `VatCategory`, `PaymentMethodType`,
  `IncomeClassificationCategory`, `IncomeClassificationType`, `TransmissionFailure`,
  `RejectedReason` and `MyDataStatus`. They are coerced strictly on requests and left
  uncoerced on responses.
- `InvoiceResult`, with a derived `mydata_status` and a `verification_url` that falls
  back to the Elorus page until myDATA answers.
- An exception hierarchy rooted at `ElorusFuseError`, covering configuration,
  transport, authentication, validation, myDATA rejection and protocol failures.
- PEP 561 type information.

[0.2.0]: https://github.com/attheodo/elorus-fuse-client/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/attheodo/elorus-fuse-client/releases/tag/v0.1.0

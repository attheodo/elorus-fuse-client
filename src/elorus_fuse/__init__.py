"""Unofficial Python client for the Elorus Fuse API.

Self-contained by design: nothing in this package reads global settings or depends on
a framework, so it can be embedded in any application. Callers supply a
:class:`Config`, build an :class:`InvoiceDraft`, and get back an :class:`InvoiceResult`
or an :class:`ElorusFuseError`::

    from elorus_fuse import Client, Config, Environment

    client = Client(Config(api_token=token, environment=Environment.SANDBOX))
    result = client.create_invoice(draft)

Provider documentation: https://developer.elorusfuse.gr/
"""

from .client import Client, Config
from .enums import (
    IncomeClassificationCategory,
    IncomeClassificationType,
    InvoiceSearchField,
    InvoiceSeriesFilter,
    InvoiceType,
    MyDataStatus,
    PaymentMethodType,
    RejectedReason,
    TransmissionFailure,
    VatCategory,
    VatExemptionCategory,
)
from .environments import BASE_URLS, Environment
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
from .payloads import (
    Address,
    IncomeClassification,
    InvoiceDraft,
    InvoiceLine,
    Party,
    PaymentMethod,
    quantize_amount,
    quantize_rate,
)
from .responses import InvoicePage, InvoiceResult, MyDataError

__version__ = '0.2.0'

__all__ = [
    # Client
    'BASE_URLS',
    'Client',
    'Config',
    'Environment',
    # Requests
    'Address',
    'IncomeClassification',
    'InvoiceDraft',
    'InvoiceLine',
    'Party',
    'PaymentMethod',
    'quantize_amount',
    'quantize_rate',
    # Responses
    'InvoicePage',
    'InvoiceResult',
    'MyDataError',
    # myDATA vocabularies
    'IncomeClassificationCategory',
    'IncomeClassificationType',
    'InvoiceSearchField',
    'InvoiceSeriesFilter',
    'InvoiceType',
    'MyDataStatus',
    'PaymentMethodType',
    'RejectedReason',
    'TransmissionFailure',
    'VatCategory',
    'VatExemptionCategory',
    # Errors
    'ElorusFuseAmbiguousInvoiceError',
    'ElorusFuseAuthenticationError',
    'ElorusFuseConfigurationError',
    'ElorusFuseError',
    'ElorusFuseMyDataRejectionError',
    'ElorusFuseProtocolError',
    'ElorusFuseTransportError',
    'ElorusFuseValidationError',
    # Metadata
    '__version__',
]

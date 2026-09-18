"""Unofficial Python client for the Elorus Fuse API.

Self-contained by design: nothing in this package reads global settings or depends on
a framework, so it can be embedded in any application. Callers supply an
:class:`ElorusFuseConfig`, build an :class:`InvoiceDraft`, and get back an
:class:`InvoiceResult` or an :class:`ElorusFuseError`.

Contract reference:
https://github.com/attheodo/elorus-fuse-client/blob/main/docs/api-contract.md
"""

from .client import (
    ElorusFuseClient,
    ElorusFuseConfig,
)
from .enums import (
    IncomeClassificationCategory,
    IncomeClassificationType,
    InvoiceType,
    MyDataStatus,
    PaymentMethodType,
    RejectedReason,
    TransmissionFailure,
    VatCategory,
)
from .environments import BASE_URLS, Environment
from .errors import (
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
)
from .responses import InvoiceResult, MyDataError

__version__ = '0.1.0'

__all__ = [
    'Address',
    'BASE_URLS',
    'ElorusFuseAuthenticationError',
    'ElorusFuseClient',
    'ElorusFuseConfig',
    'ElorusFuseConfigurationError',
    'ElorusFuseError',
    'ElorusFuseMyDataRejectionError',
    'ElorusFuseProtocolError',
    'ElorusFuseTransportError',
    'ElorusFuseValidationError',
    'Environment',
    'IncomeClassification',
    'IncomeClassificationCategory',
    'IncomeClassificationType',
    'InvoiceDraft',
    'InvoiceLine',
    'InvoiceResult',
    'InvoiceType',
    'MyDataError',
    'MyDataStatus',
    'Party',
    'PaymentMethod',
    'PaymentMethodType',
    'RejectedReason',
    'TransmissionFailure',
    'VatCategory',
    '__version__',
    'quantize_amount',
]

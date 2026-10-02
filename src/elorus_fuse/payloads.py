"""Request models for the Elorus Fuse invoice endpoint.

These dataclasses describe an invoice in Elorus' own terms and serialize themselves to
the JSON body ``POST /v1_0/invoice/`` expects. They hold no business rules: which VAT
category applies, how a line is described, and how invoices are numbered are all
decided by the caller.

Elorus flattens what myDATA nests and does not compute document totals on the
caller's behalf: they are required fields. ``InvoiceDraft`` derives them from its
lines so a caller cannot submit totals that disagree with the detail.

Every monetary value crosses the wire as a string with at most two decimal places.

Coded fields are coerced to the enums in :mod:`.enums` at construction, so an invalid
VAT category or income classification raises here rather than travelling to Elorus and
coming back as a rejection of a real invoice. Coercion accepts raw wire values too,
since each enum member is its own value.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any

from .enums import (
    IncomeClassificationCategory,
    IncomeClassificationType,
    InvoiceType,
    PaymentMethodType,
    VatCategory,
    VatExemptionCategory,
)

#: The rounding applied to every amount, both here and by callers computing the
#: figures they store locally, so the two can never disagree by a cent.
CENTS = Decimal('0.01')
FIVE_PLACES = Decimal('0.00001')


def _coerce(instance: object, field_name: str, enum: type[Enum]) -> None:
    """Replace a coded field with its enum member, rejecting unknown values.

    Frozen dataclasses need ``object.__setattr__`` to normalize in ``__post_init__``.
    """
    value = getattr(instance, field_name)
    try:
        object.__setattr__(instance, field_name, enum(value))
    except ValueError as exc:
        raise ValueError(
            f'{value!r} is not a valid {enum.__name__} for {field_name}.'
        ) from exc


def quantize_amount(value: Decimal) -> Decimal:
    """Round to the two decimal places Elorus accepts."""
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def quantize_rate(value: Decimal) -> Decimal:
    """Round a quantity or exchange rate to Elorus' five decimal places."""
    return Decimal(value).quantize(FIVE_PLACES, rounding=ROUND_HALF_UP)


def _amount(value: Decimal) -> str:
    return str(quantize_amount(value))


@dataclass(frozen=True)
class Address:
    street: str = ''
    number: str = ''
    postal_code: str = ''
    city: str = ''

    def as_payload(self) -> dict[str, Any]:
        return {
            'street': self.street,
            'number': self.number,
            'postal_code': self.postal_code,
            'city': self.city,
        }


@dataclass(frozen=True)
class Party:
    """An invoice counterparty or issuer.

    ``branch`` is ``0`` for a headquarters, which is what Elorus expects when a
    business has no branch structure.
    """

    vat_number: str
    name: str = ''
    country: str = ''
    branch: int = 0
    address: Address | None = None

    def as_payload(self, prefix: str) -> dict[str, Any]:
        """Serialize with Elorus' flat ``issuer_``/``cp_`` field prefixes."""
        payload: dict[str, Any] = {
            f'{prefix}_vat_number': self.vat_number,
            f'{prefix}_branch': self.branch,
        }
        if self.name:
            payload[f'{prefix}_name'] = self.name
        if self.country:
            payload[f'{prefix}_country'] = self.country
        if self.address:
            payload[f'{prefix}_address'] = self.address.as_payload()
        return payload


@dataclass(frozen=True)
class IncomeClassification:
    """A myDATA income classification, e.g. ``category1_3`` / ``E3_561_001``."""

    category: IncomeClassificationCategory
    type: IncomeClassificationType
    amount: Decimal

    def __post_init__(self) -> None:
        _coerce(self, 'category', IncomeClassificationCategory)
        _coerce(self, 'type', IncomeClassificationType)

    def as_payload(self) -> dict[str, Any]:
        return {
            'category': self.category.value,
            'type': self.type.value,
            'amount': _amount(self.amount),
        }


@dataclass(frozen=True)
class InvoiceLine:
    """A single invoice line.

    ``vat_amount`` is supplied rather than derived, because the rate a
    :class:`VatCategory` stands for is fixed by legislation and not something this
    layer should encode.
    """

    description: str
    net_value: Decimal
    vat_category: VatCategory
    vat_amount: Decimal
    income_classifications: Sequence[IncomeClassification] = ()
    vat_exemption_category: VatExemptionCategory | None = None
    quantity: Decimal | None = None
    line_comments_mydata: str = ''

    def __post_init__(self) -> None:
        _coerce(self, 'vat_category', VatCategory)
        if self.vat_exemption_category is not None:
            _coerce(self, 'vat_exemption_category', VatExemptionCategory)
        if self.quantity is not None:
            quantity = Decimal(self.quantity)
            if not quantity.is_finite() or quantity <= 0:
                raise ValueError('Invoice line quantity must be greater than zero.')
        if len(self.line_comments_mydata) > 150:
            raise ValueError('myDATA line comments cannot exceed 150 characters.')

    @property
    def gross_value(self) -> Decimal:
        return quantize_amount(self.net_value) + quantize_amount(self.vat_amount)

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'description': self.description,
            'net_value': _amount(self.net_value),
            'vat_category': self.vat_category.value,
            'vat_amount': _amount(self.vat_amount),
        }
        if self.income_classifications:
            payload['income_classifications'] = [
                classification.as_payload()
                for classification in self.income_classifications
            ]
        if self.vat_exemption_category is not None:
            payload['vat_exemption_category'] = self.vat_exemption_category.value
        if self.quantity is not None:
            payload['quantity'] = str(quantize_rate(self.quantity))
        if self.line_comments_mydata:
            payload['line_comments_mydata'] = self.line_comments_mydata
        return payload


@dataclass(frozen=True)
class PaymentMethod:
    """A payment method.

    ``info`` is free text that is forwarded to myDATA.
    """

    type: PaymentMethodType
    amount: Decimal
    info: str = ''

    def __post_init__(self) -> None:
        _coerce(self, 'type', PaymentMethodType)

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'type': self.type.value,
            'amount': _amount(self.amount),
        }
        if self.info:
            payload['payment_method_info'] = self.info
        return payload


@dataclass(frozen=True)
class InvoiceDraft:
    """An invoice ready to be issued.

    ``number`` is a string because Elorus types it as one; a caller numbering
    invoices with integers should convert at the boundary.
    """

    issuer: Party
    counterparty: Party | None
    invoice_type: InvoiceType
    number: str
    issue_date: date
    lines: Sequence[InvoiceLine]
    series: str = ''
    currency: str = 'EUR'
    payment_methods: Sequence[PaymentMethod] = field(default_factory=tuple)
    exchange_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError('An invoice draft needs at least one line.')
        _coerce(self, 'invoice_type', InvoiceType)
        if self.exchange_rate is not None:
            exchange_rate = Decimal(self.exchange_rate)
            if not exchange_rate.is_finite() or exchange_rate <= 0:
                raise ValueError('Invoice exchange rate must be greater than zero.')

    @property
    def total_net_value(self) -> Decimal:
        return sum(
            (quantize_amount(line.net_value) for line in self.lines), Decimal('0')
        )

    @property
    def total_vat_amount(self) -> Decimal:
        return sum(
            (quantize_amount(line.vat_amount) for line in self.lines), Decimal('0')
        )

    @property
    def total_gross_value(self) -> Decimal:
        return self.total_net_value + self.total_vat_amount

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            **self.issuer.as_payload('issuer'),
            **(self.counterparty.as_payload('cp') if self.counterparty else {}),
            'invoice_type': self.invoice_type.value,
            'series': self.series,
            'number': self.number,
            'issue_date': self.issue_date.isoformat(),
            'currency': self.currency,
            'lines': [line.as_payload() for line in self.lines],
            'total_net_value': _amount(self.total_net_value),
            'total_vat_amount': _amount(self.total_vat_amount),
            'total_gross_value': _amount(self.total_gross_value),
        }
        if self.payment_methods:
            payload['payment_methods'] = [
                method.as_payload() for method in self.payment_methods
            ]
        if self.exchange_rate is not None:
            payload['exchange_rate'] = str(quantize_rate(self.exchange_rate))
        return payload

"""Shared fixtures.

The VAT numbers used across the suite, ``123456789`` for the issuer and ``987654321``
for the counterparty, are placeholders rather than real businesses.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from elorus_fuse import (
    Address,
    IncomeClassification,
    InvoiceDraft,
    InvoiceLine,
    Party,
    PaymentMethod,
)

DraftFactory = Callable[..., InvoiceDraft]


@pytest.fixture
def make_draft() -> DraftFactory:
    """Build a representative invoice for services rendered, with overrides."""

    def factory(**overrides: Any) -> InvoiceDraft:
        defaults: dict[str, Any] = dict(
            issuer=Party(vat_number='123456789', branch=0),
            counterparty=Party(
                vat_number='987654321',
                name='ΠΑΡΑΔΕΙΓΜΑ ΑΕ',
                country='GR',
                branch=0,
                address=Address(
                    street='Εγνατία',
                    number='15',
                    postal_code='54625',
                    city='Θεσσαλονίκη',
                ),
            ),
            invoice_type='2.1',
            series='A',
            number='141',
            issue_date=date(2026, 9, 4),
            lines=[
                InvoiceLine(
                    description='Παροχή συμβουλευτικών υπηρεσιών',
                    net_value=Decimal('100.00'),
                    vat_category=1,
                    vat_amount=Decimal('24.00'),
                    income_classifications=[
                        IncomeClassification(
                            category='category1_3',
                            type='E3_561_001',
                            amount=Decimal('100.00'),
                        )
                    ],
                )
            ],
            payment_methods=[
                PaymentMethod(
                    type=5,
                    amount=Decimal('124.00'),
                    info='Κατάθεση σε λογαριασμό τράπεζας',
                )
            ],
        )
        defaults.update(overrides)
        return InvoiceDraft(**defaults)

    return factory

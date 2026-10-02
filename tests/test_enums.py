"""Tests for the myDATA vocabularies and the coercion built on them.

Two properties matter and are asserted here: naming the codes must not change what
goes on the wire, and an invalid code must fail while the draft is built rather than
when Elorus answers.
"""

import json
from collections.abc import Callable
from decimal import Decimal

import pytest

from elorus_fuse import (
    IncomeClassification,
    IncomeClassificationCategory,
    IncomeClassificationType,
    InvoiceDraft,
    InvoiceLine,
    InvoiceResult,
    InvoiceType,
    MyDataStatus,
    PaymentMethod,
    PaymentMethodType,
    RejectedReason,
    TransmissionFailure,
    VatCategory,
    VatExemptionCategory,
)

DraftFactory = Callable[..., InvoiceDraft]

# A member must *be* its wire value, so nothing downstream needs to unwrap it.


def test_int_enums_are_their_codes() -> None:
    assert VatCategory.VAT_24 == 1
    assert PaymentMethodType.ON_CREDIT == 5
    assert TransmissionFailure.PROVIDER_TO_MYDATA == 2
    assert RejectedReason.ALREADY_SUBMITTED == 3
    assert VatExemptionCategory.ARTICLE_57_OSS_EU == 30


def test_vat_exemption_vocabulary_covers_each_code_once() -> None:
    assert len(VatExemptionCategory) == 31
    assert {member.value for member in VatExemptionCategory} == set(range(1, 32))


def test_str_enums_are_their_codes() -> None:
    assert InvoiceType.SERVICES_RENDERED == '2.1'
    assert IncomeClassificationCategory.SERVICES == 'category1_3'
    assert IncomeClassificationType.E3_561_001 == 'E3_561_001'
    assert MyDataStatus.NOT_SUBMITTED == 'not_submitted'


def test_members_serialize_as_bare_values() -> None:
    # A member that serialized as "VatCategory.VAT_24" would be rejected by Elorus.
    assert json.dumps(VatCategory.VAT_24) == '1'
    assert json.dumps(InvoiceType.SERVICES_RENDERED) == '"2.1"'


# Coercion


def test_raw_values_are_normalized_to_members() -> None:
    line = InvoiceLine(
        description='Υπηρεσίες',
        net_value=Decimal('100.00'),
        vat_category=1,
        vat_amount=Decimal('24.00'),
    )

    assert line.vat_category is VatCategory.VAT_24


def test_naming_a_code_does_not_change_the_payload(make_draft: DraftFactory) -> None:
    raw = make_draft().as_payload()
    named = make_draft(
        invoice_type=InvoiceType.SERVICES_RENDERED,
        lines=[
            InvoiceLine(
                description=raw['lines'][0]['description'],
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
        payment_methods=[
            PaymentMethod(
                type=PaymentMethodType.ON_CREDIT,
                amount=Decimal('124.00'),
                info='Κατάθεση σε λογαριασμό τράπεζας',
            )
        ],
    ).as_payload()

    assert json.dumps(raw, sort_keys=True) == json.dumps(named, sort_keys=True)


# Every coded field rejects a value myDATA would not recognize.


def test_unknown_vat_category() -> None:
    with pytest.raises(ValueError, match='VatCategory'):
        InvoiceLine(
            description='x',
            net_value=Decimal('1'),
            vat_category=99,
            vat_amount=Decimal('0'),
        )


def test_unknown_payment_method_type() -> None:
    with pytest.raises(ValueError):
        PaymentMethod(type=99, amount=Decimal('1'))


def test_unknown_invoice_type(make_draft: DraftFactory) -> None:
    # '2.10' is a plausible typo for '2.1' that Elorus would reject at issuance.
    with pytest.raises(ValueError):
        make_draft(invoice_type='2.10')


def test_unknown_income_classification_category() -> None:
    with pytest.raises(ValueError):
        IncomeClassification(
            category='category9_9',
            type=IncomeClassificationType.E3_561_001,
            amount=Decimal('1'),
        )


def test_unknown_income_classification_type() -> None:
    with pytest.raises(ValueError):
        IncomeClassification(
            category=IncomeClassificationCategory.SERVICES,
            type='E3_999',
            amount=Decimal('1'),
        )


# Provider-owned codes are never coerced: parsing must survive the unexpected.


def test_unknown_transmission_failure_does_not_raise() -> None:
    result = InvoiceResult.from_payload(
        {'uid': 'ABC', 'mark': 1, 'transmission_failure': 77}
    )

    assert result.transmission_failure == 77


def test_unknown_rejected_reason_does_not_raise() -> None:
    result = InvoiceResult.from_payload({'uid': 'ABC', 'rejected_reason': 42})

    assert result.rejected_reason == 42
    assert result.mydata_status == MyDataStatus.REJECTED


def test_known_codes_still_compare_against_the_enum() -> None:
    # Leaving the field a plain int costs nothing, because members are ints.
    result = InvoiceResult.from_payload(
        {'uid': 'ABC', 'transmission_failure': 2, 'rejected_reason': 3}
    )

    assert result.transmission_failure == TransmissionFailure.PROVIDER_TO_MYDATA
    assert result.rejected_reason == RejectedReason.ALREADY_SUBMITTED

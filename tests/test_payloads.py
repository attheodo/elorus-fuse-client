"""Tests for the Elorus Fuse request models."""

from collections.abc import Callable
from decimal import Decimal

import pytest

from elorus_fuse import InvoiceDraft, InvoiceLine, Party, quantize_amount

DraftFactory = Callable[..., InvoiceDraft]

# quantize_amount


def test_rounds_half_up_not_half_even() -> None:
    # Decimal's default rounding would turn 0.125 into 0.12, understating tax.
    assert quantize_amount(Decimal('0.125')) == Decimal('0.13')
    assert quantize_amount(Decimal('0.135')) == Decimal('0.14')


def test_pads_to_two_places() -> None:
    assert str(quantize_amount(Decimal('5'))) == '5.00'


# InvoiceDraft.as_payload


def test_builds_the_documented_field_names(make_draft: DraftFactory) -> None:
    payload = make_draft().as_payload()

    assert payload['issuer_vat_number'] == '123456789'
    assert payload['issuer_branch'] == 0
    assert payload['cp_vat_number'] == '987654321'
    assert payload['cp_name'] == 'ΠΑΡΑΔΕΙΓΜΑ ΑΕ'
    assert payload['cp_country'] == 'GR'
    assert payload['cp_branch'] == 0
    assert payload['cp_address'] == {
        'street': 'Εγνατία',
        'number': '15',
        'postal_code': '54625',
        'city': 'Θεσσαλονίκη',
    }
    assert payload['invoice_type'] == '2.1'
    assert payload['series'] == 'A'
    assert payload['number'] == '141'
    assert payload['issue_date'] == '2026-09-04'
    assert payload['currency'] == 'EUR'


def test_line_carries_vat_category_and_income_classification(
    make_draft: DraftFactory,
) -> None:
    (line,) = make_draft().as_payload()['lines']

    assert line['net_value'] == '100.00'
    assert line['vat_category'] == 1
    assert line['vat_amount'] == '24.00'
    assert line['income_classifications'] == [
        {'category': 'category1_3', 'type': 'E3_561_001', 'amount': '100.00'}
    ]


def test_payment_method_is_due_on_credit_with_bank_note(
    make_draft: DraftFactory,
) -> None:
    (method,) = make_draft().as_payload()['payment_methods']

    assert method['type'] == 5
    assert method['amount'] == '124.00'
    assert method['payment_method_info'] == 'Κατάθεση σε λογαριασμό τράπεζας'


def test_totals_are_derived_from_the_lines(make_draft: DraftFactory) -> None:
    payload = make_draft().as_payload()

    assert payload['total_net_value'] == '100.00'
    assert payload['total_vat_amount'] == '24.00'
    assert payload['total_gross_value'] == '124.00'


def test_amounts_serialize_as_two_place_strings(make_draft: DraftFactory) -> None:
    # A fee of 83.33 attracts 19.9992 in VAT, which must not leak four decimal places
    # into the payload.
    payload = make_draft(
        lines=[
            InvoiceLine(
                description='Υπηρεσίες',
                net_value=Decimal('83.333'),
                vat_category=1,
                vat_amount=Decimal('19.9992'),
            )
        ]
    ).as_payload()

    assert payload['lines'][0]['net_value'] == '83.33'
    assert payload['lines'][0]['vat_amount'] == '20.00'
    assert payload['total_net_value'] == '83.33'
    assert payload['total_vat_amount'] == '20.00'
    assert payload['total_gross_value'] == '103.33'


def test_totals_sum_rounded_lines_not_rounded_sums(make_draft: DraftFactory) -> None:
    # Two lines of 0.125 round to 0.13 each, so the total is 0.26 and not the 0.25
    # that rounding the raw sum would produce.
    payload = make_draft(
        lines=[
            InvoiceLine(
                description=f'Line {index}',
                net_value=Decimal('0.125'),
                vat_category=1,
                vat_amount=Decimal('0.03'),
            )
            for index in range(2)
        ]
    ).as_payload()

    assert payload['total_net_value'] == '0.26'
    assert payload['total_gross_value'] == '0.32'


def test_optional_blocks_are_omitted_rather_than_sent_empty(
    make_draft: DraftFactory,
) -> None:
    payload = make_draft(
        payment_methods=(),
        counterparty=Party(vat_number='987654321'),
        lines=[
            InvoiceLine(
                description='Υπηρεσίες',
                net_value=Decimal('10.00'),
                vat_category=1,
                vat_amount=Decimal('2.40'),
            )
        ],
    ).as_payload()

    assert 'payment_methods' not in payload
    assert 'cp_address' not in payload
    assert 'cp_name' not in payload
    assert 'income_classifications' not in payload['lines'][0]


def test_a_draft_without_lines_is_rejected(make_draft: DraftFactory) -> None:
    with pytest.raises(ValueError):
        make_draft(lines=[])

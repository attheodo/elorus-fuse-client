"""Tests for the Elorus Fuse request models."""

from collections.abc import Callable
from decimal import Decimal

import pytest

from elorus_fuse import (
    Address,
    IncomeClassification,
    InvoiceDraft,
    InvoiceLine,
    Party,
    VatExemptionCategory,
    quantize_amount,
    quantize_rate,
)

DraftFactory = Callable[..., InvoiceDraft]

# quantize_amount


def test_rounds_half_up_not_half_even() -> None:
    # Decimal's default rounding would turn 0.125 into 0.12, understating tax.
    assert quantize_amount(Decimal('0.125')) == Decimal('0.13')
    assert quantize_amount(Decimal('0.135')) == Decimal('0.14')


def test_pads_to_two_places() -> None:
    assert str(quantize_amount(Decimal('5'))) == '5.00'


def test_quantize_rate_rounds_half_up_and_pads() -> None:
    assert str(quantize_rate(Decimal('1.234565'))) == '1.23457'
    assert str(quantize_rate(Decimal('1'))) == '1.00000'


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


def test_legacy_payload_is_unchanged(make_draft: DraftFactory) -> None:
    assert make_draft().as_payload() == {
        'issuer_vat_number': '123456789',
        'issuer_branch': 0,
        'cp_vat_number': '987654321',
        'cp_branch': 0,
        'cp_name': 'ΠΑΡΑΔΕΙΓΜΑ ΑΕ',
        'cp_country': 'GR',
        'cp_address': {
            'street': 'Εγνατία',
            'number': '15',
            'postal_code': '54625',
            'city': 'Θεσσαλονίκη',
        },
        'invoice_type': '2.1',
        'series': 'A',
        'number': '141',
        'issue_date': '2026-09-04',
        'currency': 'EUR',
        'lines': [
            {
                'description': 'Παροχή συμβουλευτικών υπηρεσιών',
                'net_value': '100.00',
                'vat_category': 1,
                'vat_amount': '24.00',
                'income_classifications': [
                    {
                        'category': 'category1_3',
                        'type': 'E3_561_001',
                        'amount': '100.00',
                    }
                ],
            }
        ],
        'total_net_value': '100.00',
        'total_vat_amount': '24.00',
        'total_gross_value': '124.00',
        'payment_methods': [
            {
                'type': 5,
                'amount': '124.00',
                'payment_method_info': 'Κατάθεση σε λογαριασμό τράπεζας',
            }
        ],
    }


def test_new_line_and_draft_fields_serialize_only_when_set(
    make_draft: DraftFactory,
) -> None:
    line = InvoiceLine(
        'Service',
        Decimal('10'),
        7,
        Decimal('0'),
        vat_exemption_category=30,
        quantity=Decimal('1.234565'),
        line_comments_mydata='[42] Package',
    )
    draft = make_draft(lines=[line], exchange_rate=Decimal('1.234565'))
    payload = draft.as_payload()

    assert line.vat_exemption_category is VatExemptionCategory.ARTICLE_57_OSS_EU
    assert payload['lines'][0] == {
        'description': 'Service',
        'net_value': '10.00',
        'vat_category': 7,
        'vat_amount': '0.00',
        'vat_exemption_category': 30,
        'quantity': '1.23457',
        'line_comments_mydata': '[42] Package',
    }
    assert payload['exchange_rate'] == '1.23457'
    assert make_draft(exchange_rate=Decimal('1')).as_payload()['exchange_rate'] == (
        '1.00000'
    )


@pytest.mark.parametrize('value', ['0', '-1', 'NaN', 'Infinity'])
def test_nonpositive_or_nonfinite_quantity_and_exchange_rate_are_rejected(
    make_draft: DraftFactory, value: str
) -> None:
    with pytest.raises(ValueError):
        InvoiceLine('Service', Decimal('1'), 1, Decimal('0'), quantity=Decimal(value))
    with pytest.raises(ValueError):
        make_draft(exchange_rate=Decimal(value))


def test_invalid_exemption_and_overlong_comment_are_rejected() -> None:
    with pytest.raises(ValueError):
        InvoiceLine('Service', Decimal('1'), 7, Decimal('0'), vat_exemption_category=32)
    InvoiceLine(
        'Service', Decimal('1'), 7, Decimal('0'), line_comments_mydata='x' * 150
    )
    with pytest.raises(ValueError):
        InvoiceLine(
            'Service', Decimal('1'), 7, Decimal('0'), line_comments_mydata='x' * 151
        )


def test_retail_omits_all_counterparty_fields_but_keeps_issuer_address(
    make_draft: DraftFactory,
) -> None:
    issuer = Party('123456789', address=Address(city='Athens'))
    payload = make_draft(issuer=issuer, counterparty=None).as_payload()

    assert not any(key.startswith('cp_') for key in payload)
    assert payload['issuer_address']['city'] == 'Athens'


@pytest.mark.parametrize(
    ('invoice_type', 'vat_category', 'exemption', 'income_type', 'retail'),
    [
        ('11.1', 1, None, 'E3_561_003', True),
        ('11.1', 7, 30, 'E3_561_007', True),
        ('11.1', 7, 4, 'E3_561_006', True),
        ('2.1', 1, None, 'E3_561_001', False),
        ('2.2', 7, 14, 'E3_561_005', False),
        ('2.3', 7, 8, 'E3_561_006', False),
    ],
)
def test_vbg_mapping_payloads(
    make_draft: DraftFactory,
    invoice_type: str,
    vat_category: int,
    exemption: int | None,
    income_type: str,
    retail: bool,
) -> None:
    classification = IncomeClassification('category1_3', income_type, Decimal('100'))
    line = InvoiceLine(
        'Stripe package',
        Decimal('100'),
        vat_category,
        Decimal('24') if vat_category == 1 else Decimal('0'),
        income_classifications=[classification],
        vat_exemption_category=exemption,
        quantity=Decimal('2') if retail else None,
        line_comments_mydata='[purchase-42] Package',
    )
    issuer = Party('123456789', address=Address(street='Main', city='Athens'))
    counterpart = None if retail else Party('987654321', country='GR')
    payload = make_draft(
        issuer=issuer,
        counterparty=counterpart,
        invoice_type=invoice_type,
        lines=[line],
        payment_methods=(),
    ).as_payload()
    expected_line = {
        'description': 'Stripe package',
        'net_value': '100.00',
        'vat_category': vat_category,
        'vat_amount': '24.00' if vat_category == 1 else '0.00',
        'income_classifications': [
            {'category': 'category1_3', 'type': income_type, 'amount': '100.00'}
        ],
        'line_comments_mydata': '[purchase-42] Package',
    }
    if exemption is not None:
        expected_line['vat_exemption_category'] = exemption
    if retail:
        expected_line['quantity'] = '2.00000'
    expected_payload = {
        'issuer_vat_number': '123456789',
        'issuer_branch': 0,
        'issuer_address': {
            'street': 'Main',
            'number': '',
            'postal_code': '',
            'city': 'Athens',
        },
        'invoice_type': invoice_type,
        'series': 'A',
        'number': '141',
        'issue_date': '2026-09-04',
        'currency': 'EUR',
        'lines': [expected_line],
        'total_net_value': '100.00',
        'total_vat_amount': '24.00' if vat_category == 1 else '0.00',
        'total_gross_value': '124.00' if vat_category == 1 else '100.00',
    }
    if counterpart is not None:
        expected_payload.update(
            {'cp_vat_number': '987654321', 'cp_branch': 0, 'cp_country': 'GR'}
        )
    assert payload == expected_payload

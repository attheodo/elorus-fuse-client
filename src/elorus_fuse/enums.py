"""myDATA vocabularies as Elorus Fuse spells them.

Every value here is fixed by Greek tax legislation and reproduced verbatim from the
Elorus Fuse OpenAPI document, so these enumerations are closed sets rather than
suggestions. Naming them buys two things: a payload that reads as tax domain language
instead of magic numbers, and validation that fires while building a draft rather than
as a provider rejection of a real invoice.

Each enum subclasses ``int``/``str``, so a member *is* its wire value: raw values keep
working, ``json`` serializes them transparently, and a response field left as a plain
integer still compares equal to the matching member.

Request-side values are coerced strictly by the payload dataclasses, because an
invalid one is a bug in the calling code. Response-side values are deliberately *not*
coerced: the provider owns those, and an unrecognized code must never crash response
parsing.

Regenerate against a newer API version before trusting these for a new document type.

Contract reference:
https://github.com/attheodo/elorus-fuse-client/blob/main/docs/api-contract.md
"""

from enum import IntEnum, StrEnum


class InvoiceType(StrEnum):
    """Document type, per the myDATA specification."""

    #: Sales Invoice
    SALES = '1.1'
    #: Sales Invoice / Intra-community Supplies
    SALES_INTRA_COMMUNITY = '1.2'
    #: Sales Invoice / Third Country Supplies
    SALES_THIRD_COUNTRY = '1.3'
    #: Sales Invoice / Sale on Behalf of Third Parties
    SALES_ON_BEHALF_OF_THIRD_PARTIES = '1.4'
    #: Sales Invoice / Clearance of Sales on Behalf of Third Parties - Fees from Sales on Behalf of Third Parties
    SALES_CLEARANCE_ON_BEHALF_OF_THIRD_PARTIES = '1.5'
    #: Sales Invoice / Supplemental Accounting Source Document
    SALES_SUPPLEMENTAL = '1.6'
    #: Invoice for Services Rendered
    SERVICES_RENDERED = '2.1'
    #: Invoice for Services Rendered / Intra-community
    SERVICES_RENDERED_INTRA_COMMUNITY = '2.2'
    #: Invoice for Services Rendered / Third Country
    SERVICES_RENDERED_THIRD_COUNTRY = '2.3'
    #: Invoice for Services Rendered / Supplemental Accounting Source Document
    SERVICES_RENDERED_SUPPLEMENTAL = '2.4'
    #: Proof of Expenditure (non-liable Issuer)
    PROOF_OF_EXPENDITURE_NON_LIABLE_ISSUER = '3.1'
    #: Proof of Expenditure (denial of issuance by liable Issuer)
    PROOF_OF_EXPENDITURE_ISSUANCE_DENIED = '3.2'
    #: Credit Invoice / Associated
    CREDIT_ASSOCIATED = '5.1'
    #: Credit Invoice / Non-Associated
    CREDIT_NON_ASSOCIATED = '5.2'
    #: Self-Delivery Record
    SELF_DELIVERY_RECORD = '6.1'
    #: Self-Supply Record
    SELF_SUPPLY_RECORD = '6.2'
    #: Contract - Income
    CONTRACT_INCOME = '7.1'
    #: Rents - Income
    RENTS_INCOME = '8.1'
    #: Climate Crisis Resilience Tax
    CLIMATE_CRISIS_RESILIENCE_TAX = '8.2'
    #: POS Payment Receipt
    POS_PAYMENT_RECEIPT = '8.4'
    #: POS Payment Return Receipt
    POS_PAYMENT_RETURN_RECEIPT = '8.5'
    #: F&B Order Form
    FOOD_AND_BEVERAGE_ORDER_FORM = '8.6'
    #: Associated Delivery Note
    DELIVERY_NOTE_ASSOCIATED = '9.1'
    #: Aggregate Delivery Note
    DELIVERY_NOTE_AGGREGATE = '9.2'
    #: Delivery Note
    DELIVERY_NOTE = '9.3'
    #: Goods Receipt / Associated
    GOODS_RECEIPT_ASSOCIATED = '10.1'
    #: Goods Receipt / Non-Associated
    GOODS_RECEIPT_NON_ASSOCIATED = '10.2'
    #: Retail Sales Receipt
    RETAIL_SALES_RECEIPT = '11.1'
    #: Receipt for Services Rendered
    RETAIL_SERVICES_RECEIPT = '11.2'
    #: Simplified Invoice
    SIMPLIFIED_INVOICE = '11.3'
    #: Retail Sales Credit Note
    RETAIL_SALES_CREDIT_NOTE = '11.4'
    #: Retail Sales Receipt on Behalf of Third Parties
    RETAIL_SALES_RECEIPT_ON_BEHALF_OF_THIRD_PARTIES = '11.5'


class VatCategory(IntEnum):
    """VAT bracket. A code, not a rate: the percentage each stands for is statutory."""

    #: VAT rate 24%
    VAT_24 = 1
    #: VAT rate 13%
    VAT_13 = 2
    #: VAT rate 6%
    VAT_6 = 3
    #: VAT rate 17%
    VAT_17 = 4
    #: VAT rate 9%
    VAT_9 = 5
    #: VAT rate 4%
    VAT_4 = 6
    #: VAT rate 0%
    VAT_0 = 7
    #: Records without VAT
    WITHOUT_VAT = 8
    #: VAT rate 3% (Article 31 of Law 5057/2023)
    VAT_3_LAW_5057 = 9
    #: VAT rate 4% (Article 31 of Law 5057/2023)
    VAT_4_LAW_5057 = 10


class PaymentMethodType(IntEnum):
    """How the invoice is settled."""

    #: Domestic Payments Account
    DOMESTIC_ACCOUNT = 1
    #: Foreign Payments Account
    FOREIGN_ACCOUNT = 2
    #: Cash
    CASH = 3
    #: Cheque
    CHEQUE = 4
    #: Due on credit
    ON_CREDIT = 5
    #: Web Banking
    WEB_BANKING = 6
    #: POS / e-POS
    POS = 7
    #: IRIS Direct Payment
    IRIS = 8


class IncomeClassificationCategory(StrEnum):
    """Income classification category."""

    #: 1.1: Commodity Sale Income
    COMMODITY_SALES = 'category1_1'
    #: 1.2: Product Sale Income
    PRODUCT_SALES = 'category1_2'
    #: 1.3: Provision of Services Income
    SERVICES = 'category1_3'
    #: 1.4: Sale of Fixed Assets Income
    FIXED_ASSET_SALES = 'category1_4'
    #: 1.5: Other Income / Profits
    OTHER_INCOME = 'category1_5'
    #: 1.6: Self-Deliveries / Self-Supplies
    SELF_DELIVERIES = 'category1_6'
    #: 1.7: Income on behalf of Third Parties
    ON_BEHALF_OF_THIRD_PARTIES = 'category1_7'
    #: 1.8: Past fiscal years income
    PAST_FISCAL_YEARS = 'category1_8'
    #: 1.9: Future fiscal years income
    FUTURE_FISCAL_YEARS = 'category1_9'
    #: 1.10: Other Income Adjustment / Regularisation Entries
    ADJUSTMENTS = 'category1_10'
    #: 1.95: Other Income-related Information
    OTHER_INFORMATION = 'category1_95'
    #: 3: Transport
    TRANSPORT = 'category3'


class IncomeClassificationType(StrEnum):
    """Income classification E3 code.

    The codes are themselves the domain vocabulary, so they are their own names.
    """

    #: E3_106: Self-Production of fixed assets - Self-deliveries - Destroying inventory / Commodities
    E3_106 = 'E3_106'
    #: E3_205: Self-production of fixed assets - Self-deliveries - Destroying inventory / Raw and other materials
    E3_205 = 'E3_205'
    #: E3_210: Self-production of fixed assets - Self-deliveries - Destroying inventory / Products and production in progress
    E3_210 = 'E3_210'
    #: E3_305: Self-production of fixed assets - Self-deliveries - Destroying inventory / Raw and other materials
    E3_305 = 'E3_305'
    #: E3_310: Self-production of fixed assets - Self-deliveries - Destroying inventory / Products and production in progress
    E3_310 = 'E3_310'
    #: E3_318: Self-production of fixed assets - Self-deliveries - Destroying inventory / Production expenses
    E3_318 = 'E3_318'
    #: E3_561_001: Wholesale Sales of Goods and Services - for Traders
    E3_561_001 = 'E3_561_001'
    #: E3_561_002: Wholesale Sales of Goods and Services pursuant to article 39a paragraph 5 of the VAT Code (Law 2859/2000)
    E3_561_002 = 'E3_561_002'
    #: E3_561_003: Retail Sales of Goods and Services - Private Clientele
    E3_561_003 = 'E3_561_003'
    #: E3_561_004: Retail Sales of Goods and Services pursuant to article 39a paragraph 5 of the VAT Code (Law 2859/2000)
    E3_561_004 = 'E3_561_004'
    #: E3_561_005: Intra-Community Foreign Sales of Goods and Services
    E3_561_005 = 'E3_561_005'
    #: E3_561_006: Third Country Foreign Sales of Goods and Services
    E3_561_006 = 'E3_561_006'
    #: E3_561_007: Other Sales of Goods and Services
    E3_561_007 = 'E3_561_007'
    #: E3_562: Other Ordinary Income
    E3_562 = 'E3_562'
    #: E3_563: Credit Interest and Related Income
    E3_563 = 'E3_563'
    #: E3_564: Credit Exchange Differences
    E3_564 = 'E3_564'
    #: E3_565: Income from Participation
    E3_565 = 'E3_565'
    #: E3_566: Profits from Disposing Non-Current Assets
    E3_566 = 'E3_566'
    #: E3_567: Profits from the Reversal of Provisions and Impairments
    E3_567 = 'E3_567'
    #: E3_568: Profits from Measurement at Fair Value
    E3_568 = 'E3_568'
    #: E3_570: Extraordinary income and profits
    E3_570 = 'E3_570'
    #: E3_595: Self-Production Expenses
    E3_595 = 'E3_595'
    #: E3_596: Subsidies - Grants
    E3_596 = 'E3_596'
    #: E3_597: Subsidies - Grants for Investment Purposes - Expense Coverage
    E3_597 = 'E3_597'
    #: E3_880_001: Wholesale Sales of Fixed Assets
    E3_880_001 = 'E3_880_001'
    #: E3_880_002: Retail Sales of Fixed Assets
    E3_880_002 = 'E3_880_002'
    #: E3_880_003: Intra-Community Foreign Sales of Fixed Assets
    E3_880_003 = 'E3_880_003'
    #: E3_880_004: Third Country Foreign Sales of Fixed Assets
    E3_880_004 = 'E3_880_004'
    #: E3_881_001: Wholesale Sales on behalf of Third Parties
    E3_881_001 = 'E3_881_001'
    #: E3_881_002: Retail Sales on behalf of Third Parties
    E3_881_002 = 'E3_881_002'
    #: E3_881_003: Intra-Community Foreign Sales on behalf of Third Parties
    E3_881_003 = 'E3_881_003'
    #: E3_881_004: Third Country Foreign Sales on behalf of Third Parties
    E3_881_004 = 'E3_881_004'
    #: E3_598_001: Sales of goods under the terms of EFK
    E3_598_001 = 'E3_598_001'
    #: E3_598_003: Sales on behalf of farmers via agricultural collaboration etc.
    E3_598_003 = 'E3_598_003'
    #: Without E3 type
    E3_NULL = 'E3_NULL'


class TransmissionFailure(IntEnum):
    """Why a document could not be transmitted in real time.

    Only ``ENTITY_TO_PROVIDER`` and ``DECISION_1138_2020`` may be *sent*;
    ``PROVIDER_TO_MYDATA`` is reported back by Elorus when it accepted an invoice it
    could not immediately forward to myDATA.
    """

    #: The entity is unable to communicate with the e-invoicing provider
    ENTITY_TO_PROVIDER = 1
    #: The e-invoicing provider is unable to communicate with myDATA
    PROVIDER_TO_MYDATA = 2
    #: Entities of case c', par. 1, article 5 of Decision 1138/2020
    DECISION_1138_2020 = 4


class RejectedReason(IntEnum):
    """Why myDATA refused a document."""

    #: Business errors
    BUSINESS_ERRORS = 1
    #: Invalid data
    INVALID_DATA = 2
    #: Already submitted
    ALREADY_SUBMITTED = 3


class MyDataStatus(StrEnum):
    """Where a document stands with myDATA.

    The values mirror the vocabulary Elorus uses for its own ``mydata_status`` filter,
    so a status derived locally can be fed straight back to the list endpoint.
    """

    #: myDATA acknowledged the document and returned a MARK.
    SUCCESS = 'success'
    #: Elorus holds the document but myDATA has not answered yet.
    NOT_SUBMITTED = 'not_submitted'
    #: myDATA refused the document.
    REJECTED = 'rejected'

"""Tests guarding the package's public surface."""

from importlib.metadata import version

import elorus_fuse
from elorus_fuse import (
    ElorusFuseDuplicateInvoiceError,
    VatExemptionCategory,
    quantize_rate,
)


def test_every_name_in_all_is_exported() -> None:
    missing = [name for name in elorus_fuse.__all__ if not hasattr(elorus_fuse, name)]

    assert missing == []


def test_all_has_no_duplicates() -> None:
    assert len(elorus_fuse.__all__) == len(set(elorus_fuse.__all__))


def test_new_public_names_are_exported() -> None:
    assert (
        elorus_fuse.ElorusFuseDuplicateInvoiceError is ElorusFuseDuplicateInvoiceError
    )
    assert elorus_fuse.VatExemptionCategory is VatExemptionCategory
    assert elorus_fuse.quantize_rate is quantize_rate


def test_version_matches_the_installed_distribution() -> None:
    assert elorus_fuse.__version__ == version('elorus-fuse-client')

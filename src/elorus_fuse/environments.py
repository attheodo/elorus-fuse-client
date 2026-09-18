"""The Elorus Fuse environments and the hosts they live on.

Sandbox and production are separate deployments on separate domains, each with its
own API key. Selecting an environment is therefore the single decision that
determines whether a call issues a real, legally binding invoice, which is why
:class:`ElorusFuseConfig` requires one rather than defaulting.
"""

from enum import StrEnum


class Environment(StrEnum):
    """Which Elorus Fuse deployment to talk to."""

    #: Issues nothing real. Supports the ``FAIL-500`` invoice series, which
    #: simulates myDATA being unavailable.
    SANDBOX = 'sandbox'
    #: Issues real invoices and forwards them to myDATA.
    PRODUCTION = 'production'

    @property
    def base_url(self) -> str:
        return BASE_URLS[self]


BASE_URLS = {
    Environment.SANDBOX: 'https://api.fuse-staging.gr',
    Environment.PRODUCTION: 'https://api.elorusfuse.gr',
}

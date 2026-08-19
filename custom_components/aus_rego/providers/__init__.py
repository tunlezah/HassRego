"""Registration providers, one per Australian jurisdiction.

Every provider returns the same :class:`~custom_components.aus_rego.models.RegoResult`,
so the rest of the integration never needs to know which state it is talking to.
"""

from __future__ import annotations

from .act import AustralianCapitalTerritoryProvider
from .base import HttpClient, HttpResponse, ProviderField, RegoProvider
from .manual import ManualProvider
from .nsw import NewSouthWalesProvider
from .nt import NorthernTerritoryProvider
from .qld import QueenslandProvider
from .rest import RestProvider
from .sa import SouthAustraliaProvider
from .tas import TasmaniaProvider
from .vic import VictoriaProvider
from .wa import WesternAustraliaProvider

#: Instantiated once each; providers hold no per-check state.
PROVIDERS: dict[str, RegoProvider] = {
    provider.key: provider
    for provider in (
        NewSouthWalesProvider(),
        VictoriaProvider(),
        QueenslandProvider(),
        SouthAustraliaProvider(),
        WesternAustraliaProvider(),
        TasmaniaProvider(),
        NorthernTerritoryProvider(),
        AustralianCapitalTerritoryProvider(),
        ManualProvider(),
        RestProvider(),
    )
}

#: The eight real jurisdictions, in the order Australians usually list them.
JURISDICTION_KEYS: tuple[str, ...] = ("nsw", "vic", "qld", "sa", "wa", "tas", "nt", "act")

#: Providers that are not a jurisdiction, offered as fallbacks.
FALLBACK_KEYS: tuple[str, ...] = ("manual", "rest")


def get_provider(key: str) -> RegoProvider:
    """Return the provider for a jurisdiction key."""
    try:
        return PROVIDERS[key]
    except KeyError:
        raise ValueError(f"Unknown registration provider: {key!r}") from None


def provider_labels() -> dict[str, str]:
    """Return ``key -> human label`` for the config flow selector."""
    labels: dict[str, str] = {}
    for key in (*JURISDICTION_KEYS, *FALLBACK_KEYS):
        provider = PROVIDERS[key]
        label = provider.name
        if provider.gated:
            label = f"{label} (manual mode recommended)"
        labels[key] = label
    return labels


__all__ = [
    "FALLBACK_KEYS",
    "JURISDICTION_KEYS",
    "PROVIDERS",
    "HttpClient",
    "HttpResponse",
    "ProviderField",
    "RegoProvider",
    "get_provider",
    "provider_labels",
]

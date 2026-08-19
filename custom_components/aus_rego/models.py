"""Data model shared by every registration provider.

This module deliberately has no Home Assistant imports so that the status
logic can be unit tested (and reused) on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class RegoStatus(StrEnum):
    """Outcome of a registration check.

    ``UNKNOWN`` is not a negative result. It means the check itself did not
    produce an answer, and callers must never treat it as "not registered".
    """

    REGISTERED = "registered"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    UNREGISTERED = "unregistered"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


#: Statuses that answer the question "is this vehicle registered?" with "no".
NEGATIVE_STATUSES: frozenset[RegoStatus] = frozenset(
    {
        RegoStatus.EXPIRED,
        RegoStatus.SUSPENDED,
        RegoStatus.CANCELLED,
        RegoStatus.UNREGISTERED,
        RegoStatus.NOT_FOUND,
    }
)


@dataclass(slots=True)
class RegoResult:
    """Normalised result of a registration check."""

    status: RegoStatus
    plate: str
    jurisdiction: str
    expiry: date | None = None
    make: str | None = None
    model: str | None = None
    colour: str | None = None
    body_type: str | None = None
    vehicle_class: str | None = None
    ctp_insurer: str | None = None
    restrictions: list[str] = field(default_factory=list)
    #: Free-form message from the upstream service, useful for diagnostics.
    message: str | None = None
    #: Populated when ``status`` is UNKNOWN, describing why the check failed.
    error: str | None = None

    @property
    def registered(self) -> bool | None:
        """Return True/False, or None when the check produced no answer.

        Automations that act on "not registered" must check for ``False``
        explicitly rather than relying on falsiness, because ``None`` means
        "we do not know".
        """
        if self.status is RegoStatus.REGISTERED:
            return True
        if self.status in NEGATIVE_STATUSES:
            return False
        return None

    @property
    def is_conclusive(self) -> bool:
        """Return True when the upstream service actually answered."""
        return self.status is not RegoStatus.UNKNOWN

    def days_remaining(self, today: date) -> int | None:
        """Return days until expiry (negative once expired)."""
        if self.expiry is None:
            return None
        return (self.expiry - today).days

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation for events and services."""
        return {
            "status": str(self.status),
            "registered": self.registered,
            "plate": self.plate,
            "jurisdiction": self.jurisdiction,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "make": self.make,
            "model": self.model,
            "colour": self.colour,
            "body_type": self.body_type,
            "vehicle_class": self.vehicle_class,
            "ctp_insurer": self.ctp_insurer,
            "restrictions": list(self.restrictions),
            "message": self.message,
            "error": self.error,
        }

    @classmethod
    def unknown(
        cls, plate: str, jurisdiction: str, error: str, *, message: str | None = None
    ) -> RegoResult:
        """Build a result representing "the check did not answer"."""
        return cls(
            status=RegoStatus.UNKNOWN,
            plate=plate,
            jurisdiction=jurisdiction,
            error=error,
            message=message,
        )


def derive_status(
    *,
    raw_status: str | None,
    expiry: date | None,
    today: date,
    default_registered: bool = False,
) -> RegoStatus:
    """Map a jurisdiction's wording onto :class:`RegoStatus`.

    ``raw_status`` is the free text the upstream service used. When it carries
    no recognisable keyword we fall back to the expiry date, and finally to
    ``default_registered`` — which providers set to True only when the service
    returning a record at all implies a live registration.
    """
    text = (raw_status or "").strip().lower()

    # Order matters: "cancelled" and "suspended" outrank an expiry date, because
    # a suspended registration can still have a future expiry.
    if "cancel" in text:
        return RegoStatus.CANCELLED
    if "suspend" in text:
        return RegoStatus.SUSPENDED
    if "expired" in text or "lapsed" in text:
        return RegoStatus.EXPIRED
    if "unregistered" in text or "not registered" in text or "no record" in text:
        return RegoStatus.UNREGISTERED

    if "registered" in text or "current" in text or "valid" in text or text == "ok":
        # Still respect an expiry date that has already passed.
        if expiry is not None and expiry < today:
            return RegoStatus.EXPIRED
        return RegoStatus.REGISTERED

    if expiry is not None:
        return RegoStatus.REGISTERED if expiry >= today else RegoStatus.EXPIRED

    return RegoStatus.REGISTERED if default_registered else RegoStatus.UNKNOWN

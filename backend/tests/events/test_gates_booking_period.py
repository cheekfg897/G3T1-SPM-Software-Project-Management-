"""Unit tests for SCRUM-109 — both gates refuse a booking outside the event's period.

AC1: an active venue arrangement whose period isn't within the event's keeps it out of
Safety Review (SCRUM-97), and the refusal names the arrangement with the reason. AC2:
confirmation (SCRUM-49) refuses it for the same reason. AC3: a booking within the
event but shorter, such as a breakout room, is accepted. AC4: with every arrangement
within the event, Approved and unflagged, the gates behave as before, shown here by a
booking for exactly the event's period; the SCRUM-97 and SCRUM-49 suites cover the rest.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, assigned to Event Coordinator 3, from 09:00 to 17:00 on 15 October
2026, business time), so the checks are real SQL. Every booking is at ``hall``, whose id
isn't the first arrangement's, so a reason naming the venue instead fails.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.common.clock import app_timezone, as_utc
from app.common.errors import AppError
from app.modules.auth.models import User
from app.modules.events.models import EventRequest, EventRequestStatus
from app.modules.events.services import (
    EventConfirmationNotAllowedError,
    SafetyReviewNotAllowedError,
    confirm_event_request,
    submit_for_safety_review,
)
from app.modules.venue.models import BookingRequestStatus, Venue, VenueBookingRequest
from tests.conftest import approve_safety

pytestmark = pytest.mark.scrum_109

REFERENCE = "EVR-AAAAAAAA"
#: The Event Coordinator ``saved_event_request`` is assigned to.
COORDINATOR_ID = 3
#: ``saved_event_request``'s period, as a reason shows it, in business time.
EVENT_PERIOD = "2026-10-15 09:00 to 2026-10-15 17:00"

Book = Callable[..., VenueBookingRequest]


@dataclass(frozen=True)
class Gate:
    """One of the two gates: the status it moves an event on from, and to.

    ``message`` is the refusal's top line, above the reasons in its details.
    """

    name: str
    status_before: EventRequestStatus
    status_after: EventRequestStatus
    go_through: Callable[..., EventRequest]
    refusal: type[AppError]
    message: str


SAFETY_REVIEW_GATE = Gate(
    name="safety-review",
    status_before=EventRequestStatus.APPROVED,
    status_after=EventRequestStatus.SAFETY_REVIEW,
    go_through=submit_for_safety_review,
    refusal=SafetyReviewNotAllowedError,
    message=(
        "The event can go to Safety Review once every venue arrangement is approved and"
        " booked within the event's date and time, and every equipment request has an"
        " outcome from Technical Support."
    ),
)
CONFIRMATION_GATE = Gate(
    name="confirmation",
    status_before=EventRequestStatus.SAFETY_REVIEW,
    status_after=EventRequestStatus.CONFIRMED,
    go_through=confirm_event_request,
    refusal=EventConfirmationNotAllowedError,
    message=(
        "The event can be confirmed once the Safety Officer has approved it, every venue"
        " arrangement is approved and booked within the event's date and time, and every"
        " equipment request has an outcome from Technical Support."
    ),
)
BOTH_GATES = pytest.mark.parametrize(
    "gate", [SAFETY_REVIEW_GATE, CONFIRMATION_GATE], ids=lambda gate: gate.name
)


def _business(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment in October 2026, given in business time, as stored: in UTC."""
    return as_utc(datetime(2026, 10, day, hour, minute, tzinfo=app_timezone()))


def _outside_reason(arrangement: VenueBookingRequest, booked_for: str) -> str:
    """The reason a gate gives for ``arrangement``, which is for ``booked_for``."""
    return (
        f"Venue arrangement {arrangement.id} is for {booked_for}, outside the event's"
        f" {EVENT_PERIOD}."
    )


@pytest.fixture()
def at_gate(
    gate: Gate,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save: Callable[..., None],
) -> EventRequest:
    """``saved_event_request`` where ``gate`` takes it from, with the users saved.

    The Safety Officer's approval is recorded too: confirmation needs it, and the
    Safety Review gate doesn't read it.
    """
    saved_event_request.status = gate.status_before
    save(saved_event_request)
    approve_safety(saved_event_request, save)
    return saved_event_request


@pytest.fixture()
def hall(make_venue: Callable[..., Venue], save: Callable[..., None]) -> Venue:
    """The venue the event is booked at, with setup and turnaround time.

    Setup is an hour and turnaround half an hour, so a check that read the padded period
    instead of the booking's own would refuse a booking for exactly the event. Another
    venue is saved first, so the hall's id isn't the first arrangement's.
    """
    save(make_venue(name="Annexe"))
    saved = make_venue(name="Main Hall", setup_minutes=60, turnaround_minutes=30)
    save(saved)
    return saved


@pytest.fixture()
def book(at_gate: EventRequest, hall: Venue, save: Callable[..., None]) -> Book:
    """Save an arrangement for the event at ``hall``, for the period given.

    It is Approved unless ``status`` says otherwise.
    """

    def _book(
        starts_at: datetime,
        ends_at: datetime,
        status: BookingRequestStatus = BookingRequestStatus.APPROVED,
    ) -> VenueBookingRequest:
        arrangement = VenueBookingRequest(
            event_id=at_gate.id,
            venue_id=hall.id,
            starts_at=starts_at,
            ends_at=ends_at,
            purpose="Main session",
            expected_occupancy=80,
            status=status,
            requested_by=COORDINATOR_ID,
        )
        save(arrangement)
        return arrangement

    return _book


# --------------------------------------------------------------------------
# AC1, AC2 — a booking outside the event's period holds it back at either gate
# --------------------------------------------------------------------------


@BOTH_GATES
@pytest.mark.parametrize(
    ("starts_at", "ends_at", "booked_for"),
    [
        (_business(15, 8, 30), _business(15, 12), "2026-10-15 08:30 to 2026-10-15 12:00"),
        (_business(15, 13), _business(15, 17, 30), "2026-10-15 13:00 to 2026-10-15 17:30"),
        (_business(14, 9), _business(14, 17), "2026-10-14 09:00 to 2026-10-14 17:00"),
    ],
    ids=["starts-before-the-event", "ends-after-the-event", "on-the-old-date"],
)
def test_a_booking_outside_the_event_is_named_and_the_event_stays_where_it_was(
    db_session: Session,
    gate: Gate,
    at_gate: EventRequest,
    book: Book,
    reload_event_request: Callable[[int], EventRequest],
    starts_at: datetime,
    ends_at: datetime,
    booked_for: str,
) -> None:
    arrangement = book(starts_at, ends_at)

    with pytest.raises(gate.refusal) as refusal:
        gate.go_through(COORDINATOR_ID, REFERENCE, session=db_session)

    assert refusal.value.message == gate.message
    assert refusal.value.details == {
        "venue_arrangements": [_outside_reason(arrangement, booked_for)]
    }
    assert reload_event_request(at_gate.id).status is gate.status_before


@BOTH_GATES
def test_every_booking_outside_the_event_is_named_earliest_period_first(
    db_session: Session, gate: Gate, at_gate: EventRequest, book: Book
) -> None:
    """The earliest booking's period is within the event; the other two are outside.

    They are saved out of order: the one with the earlier period has the higher id.
    """
    later = book(_business(15, 16), _business(15, 18))
    earlier = book(_business(15, 13), _business(15, 17, 30))
    book(_business(15, 9), _business(15, 10))

    with pytest.raises(gate.refusal) as refusal:
        gate.go_through(COORDINATOR_ID, REFERENCE, session=db_session)

    assert refusal.value.details == {
        "venue_arrangements": [
            _outside_reason(earlier, "2026-10-15 13:00 to 2026-10-15 17:30"),
            _outside_reason(later, "2026-10-15 16:00 to 2026-10-15 18:00"),
        ]
    }


@BOTH_GATES
def test_a_pending_booking_outside_the_event_is_named_for_both_reasons(
    db_session: Session, gate: Gate, at_gate: EventRequest, book: Book
) -> None:
    """ADR-0130 decision 2: every active arrangement counts, whatever its status."""
    pending = book(_business(14, 9), _business(14, 17), BookingRequestStatus.PENDING)

    with pytest.raises(gate.refusal) as refusal:
        gate.go_through(COORDINATOR_ID, REFERENCE, session=db_session)

    assert refusal.value.details == {
        "venue_arrangements": [
            f"Venue arrangement {pending.id} is pending.",
            _outside_reason(pending, "2026-10-14 09:00 to 2026-10-14 17:00"),
        ]
    }


# --------------------------------------------------------------------------
# AC3, AC4 — a booking within the event's period lets it through
# --------------------------------------------------------------------------


@BOTH_GATES
@pytest.mark.parametrize(
    ("starts_at", "ends_at"),
    [(_business(15, 9), _business(15, 17)), (_business(15, 13), _business(15, 15))],
    ids=["exactly-the-event", "a-shorter-breakout"],
)
def test_a_booking_within_the_event_lets_it_through(
    db_session: Session,
    gate: Gate,
    at_gate: EventRequest,
    book: Book,
    reload_event_request: Callable[[int], EventRequest],
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    book(starts_at, ends_at)

    gate.go_through(COORDINATOR_ID, REFERENCE, session=db_session)

    assert reload_event_request(at_gate.id).status is gate.status_after

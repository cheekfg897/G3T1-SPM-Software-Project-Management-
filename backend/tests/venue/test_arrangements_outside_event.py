"""Unit tests for SCRUM-109 — the event's arrangements booked outside its period.

The Safety Review gate and confirmation (SCRUM-97, SCRUM-49) refuse an event while any
active arrangement's period isn't within the event's (AC1, AC2). Within, not equal: a
shorter booking, such as a breakout room, is accepted (AC3), as is one for exactly the
event's period. A retired arrangement no longer counts (ADR-0039), so it is ignored.

The services run against ``db_session``; the event is the ``saved_event`` fixture's,
from 09:00 on 1 November 2026 to 17:30 the next day, Singapore time. Its venue isn't the
first one saved, so its id isn't the first arrangement's.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.modules.venue.models import (
    RETIRED_REQUEST_STATUSES,
    BookingRequestStatus,
    Venue,
    VenueBookingRequest,
)
from app.modules.venue.services import ArrangementOutsideEvent, list_arrangements_outside_event
from tests.venue.conftest import COORDINATOR_ID, SINGAPORE, SavedEvent, at

pytestmark = pytest.mark.scrum_109

#: The ``saved_event`` fixture's period, as the reason shows it, in business time.
EVENT_PERIOD = "2026-11-01 09:00 to 2026-11-02 17:30"
#: Every status an arrangement still counts in (ADR-0039), from the enum.
ACTIVE_STATUSES = sorted(set(BookingRequestStatus) - RETIRED_REQUEST_STATUSES)


@pytest.fixture()
def arrange(
    saved_event: SavedEvent, make_venue: Callable[..., Venue], save: Callable[..., None]
) -> Callable[..., VenueBookingRequest]:
    """Save an arrangement for one event, Approved unless told so.

    Every one is at the second venue saved, so its id isn't the first arrangement's.
    """
    event = saved_event()
    save(make_venue(name="Annexe"))
    venue = make_venue()
    save(venue)

    def _arrange(
        starts_at: datetime,
        ends_at: datetime,
        status: BookingRequestStatus = BookingRequestStatus.APPROVED,
    ) -> VenueBookingRequest:
        arrangement = VenueBookingRequest(
            event_id=event.id,
            venue_id=venue.id,
            starts_at=starts_at,
            ends_at=ends_at,
            purpose="Main session",
            expected_occupancy=80,
            status=status,
            requested_by=COORDINATOR_ID,
        )
        save(arrangement)
        return arrangement

    return _arrange


def _outside(arrangement: VenueBookingRequest, session: Session) -> list[ArrangementOutsideEvent]:
    return list_arrangements_outside_event(arrangement.event_id, session=session)


@pytest.mark.parametrize("status", ACTIVE_STATUSES, ids=lambda status: status.value)
@pytest.mark.parametrize(
    ("starts_at", "ends_at", "booked_for"),
    [
        (at(8, 30), at(12), "2026-11-01 08:30 to 2026-11-01 12:00"),
        (at(13, day=2), at(18, day=2), "2026-11-02 13:00 to 2026-11-02 18:00"),
        (
            datetime(2026, 10, 31, 9, tzinfo=SINGAPORE),
            datetime(2026, 10, 31, 12, tzinfo=SINGAPORE),
            "2026-10-31 09:00 to 2026-10-31 12:00",
        ),
    ],
    ids=["starts-before-the-event", "ends-after-the-event", "on-the-old-date"],
)
def test_an_arrangement_not_within_the_event_is_listed_with_both_periods(
    db_session: Session,
    arrange: Callable[..., VenueBookingRequest],
    starts_at: datetime,
    ends_at: datetime,
    booked_for: str,
    status: BookingRequestStatus,
) -> None:
    """ADR-0130 decision 2: an active arrangement counts, whatever its status."""
    arrangement = arrange(starts_at, ends_at, status)

    outside = _outside(arrangement, db_session)

    assert outside == [
        ArrangementOutsideEvent(id=arrangement.id, booked_for=booked_for, event_period=EVENT_PERIOD)
    ]


def test_every_arrangement_outside_the_event_is_listed_earliest_period_first(
    db_session: Session, arrange: Callable[..., VenueBookingRequest]
) -> None:
    """The earliest arrangement's period is within the event; the other two are outside.

    They are saved out of order: the one with the earlier period has the higher id.
    """
    later = arrange(at(16, day=2), at(17, 45, day=2))
    earlier = arrange(at(13, day=2), at(18, day=2))
    within = arrange(at(9), at(12))

    outside = _outside(within, db_session)

    assert outside == [
        ArrangementOutsideEvent(
            id=earlier.id,
            booked_for="2026-11-02 13:00 to 2026-11-02 18:00",
            event_period=EVENT_PERIOD,
        ),
        ArrangementOutsideEvent(
            id=later.id,
            booked_for="2026-11-02 16:00 to 2026-11-02 17:45",
            event_period=EVENT_PERIOD,
        ),
    ]


@pytest.mark.parametrize(
    ("starts_at", "ends_at"),
    [(at(9), at(17, 30, day=2)), (at(13), at(16))],
    ids=["exactly-the-event", "a-shorter-breakout"],
)
def test_an_arrangement_within_the_event_is_not_listed(
    db_session: Session,
    arrange: Callable[..., VenueBookingRequest],
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    arrangement = arrange(starts_at, ends_at)

    assert _outside(arrangement, db_session) == []


@pytest.mark.parametrize(
    "status", sorted(RETIRED_REQUEST_STATUSES), ids=lambda status: status.value
)
def test_a_retired_arrangement_on_the_old_date_is_ignored(
    db_session: Session,
    arrange: Callable[..., VenueBookingRequest],
    status: BookingRequestStatus,
) -> None:
    arrangement = arrange(
        datetime(2026, 10, 31, 9, tzinfo=SINGAPORE),
        datetime(2026, 10, 31, 12, tzinfo=SINGAPORE),
        status,
    )

    assert _outside(arrangement, db_session) == []

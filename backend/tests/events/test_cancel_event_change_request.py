"""Unit tests for SCRUM-61 with SCRUM-56: cancelling closes the event's change request.

SCRUM-56 AC9: an event cancelled while a change request is Pending closes the request
as Withdrawn, noting the event was cancelled (ADR-0126). The cancellation does it in
its own commit, so the request is withdrawn with the cancellation or not at all, and
it reads the event's row under a lock first, as raising and withdrawing a change
request do, so neither can slip in between (ADR-0122). A request already decided or
withdrawn stays as it is.

Runs against ``db_session`` with ``saved_users`` and ``saved_event_request``
(``EVR-AAAAAAAA``, organiser 7's, submitted); ``save_change_request`` writes the
requests directly.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import Connection, update
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.equipment import services as equipment_services
from app.modules.events.models import (
    ChangeRequestStatus,
    EventChangeRequest,
    EventRequest,
    EventRequestStatus,
)
from app.modules.events.services import (
    CANCELLED_WITHDRAWAL_NOTE,
    EventCancellationNotAllowedError,
    cancel_event_request,
)
from tests.events.cases import LOST_CONNECTION

pytestmark = pytest.mark.scrum_61

SaveChangeRequest = Callable[..., EventChangeRequest]
ChangeRequestsOf = Callable[[int], list[EventChangeRequest]]
OnEventRowLock = Callable[[Callable[[Connection], None]], None]
ReloadEventRequest = Callable[[int], EventRequest]

REFERENCE = "EVR-AAAAAAAA"
ORGANISER_ID = 7
REASON = "Our keynote speaker has withdrawn."
#: When Coordinator 3 approved a request in the race below (SCRUM-57).
DECIDED_AT = datetime(2026, 9, 16, 1, 0, tzinfo=timezone.utc)
DECIDED_OR_WITHDRAWN = [
    status for status in ChangeRequestStatus if status is not ChangeRequestStatus.PENDING
]


@pytest.fixture()
def pending(
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
) -> EventChangeRequest:
    """A Pending change request on ``saved_event_request``."""
    return save_change_request(saved_event_request)


def _cancel(session: Session) -> EventRequest:
    return cancel_event_request(ORGANISER_ID, REFERENCE, {"reason": REASON}, session=session)


def test_a_pending_change_request_is_withdrawn_noting_the_cancellation(
    db_session: Session,
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    change_requests_of: ChangeRequestsOf,
) -> None:
    _cancel(db_session)

    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.withdrawal_note) == (
        ChangeRequestStatus.WITHDRAWN,
        CANCELLED_WITHDRAWAL_NOTE,
    )
    assert saved.withdrawn_at is not None


@pytest.mark.parametrize("status", DECIDED_OR_WITHDRAWN, ids=lambda status: status.value)
def test_a_request_no_longer_pending_is_left_as_it_is(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    save_change_request: SaveChangeRequest,
    change_requests_of: ChangeRequestsOf,
    status: ChangeRequestStatus,
) -> None:
    save_change_request(saved_event_request, status)

    _cancel(db_session)

    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.withdrawal_note) == (status, None)


def test_an_event_with_no_change_request_is_still_cancelled(
    db_session: Session,
    saved_users: list[User],
    saved_event_request: EventRequest,
    change_requests_of: ChangeRequestsOf,
    reload_event_request: ReloadEventRequest,
) -> None:
    _cancel(db_session)

    assert reload_event_request(saved_event_request.id).status is EventRequestStatus.CANCELLED
    assert change_requests_of(saved_event_request.id) == []


def test_the_request_stays_pending_if_the_cancellation_is_not_saved(
    db_session: Session,
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    change_requests_of: ChangeRequestsOf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returning the equipment comes after the withdrawal, so its failure undoes it."""

    def _fail(*_: Any, **__: Any) -> None:
        raise LOST_CONNECTION

    monkeypatch.setattr(equipment_services, "release_event_reservations", _fail)

    with pytest.raises(type(LOST_CONNECTION)):
        _cancel(db_session)
    db_session.rollback()

    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.withdrawal_note) == (ChangeRequestStatus.PENDING, None)


def test_a_request_decided_while_waiting_for_the_lock_stays_decided(
    db_session: Session,
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    on_event_row_lock: OnEventRowLock,
    change_requests_of: ChangeRequestsOf,
) -> None:
    """The coordinator's decision committed first, so the cancellation sees it."""
    approved = (
        update(EventChangeRequest)
        .where(EventChangeRequest.id == pending.id)
        .values(status=ChangeRequestStatus.APPROVED, decided_at=DECIDED_AT, decided_by=3)
    )
    on_event_row_lock(lambda connection: connection.execute(approved))

    _cancel(db_session)

    [saved] = change_requests_of(saved_event_request.id)
    assert (saved.status, saved.withdrawal_note) == (ChangeRequestStatus.APPROVED, None)


def test_an_event_rejected_while_waiting_for_the_lock_is_not_cancelled(
    db_session: Session,
    pending: EventChangeRequest,
    saved_event_request: EventRequest,
    on_event_row_lock: OnEventRowLock,
    change_requests_of: ChangeRequestsOf,
) -> None:
    """The status is checked on the row read under the lock, not the earlier copy."""
    rejected = (
        update(EventRequest)
        .where(EventRequest.id == saved_event_request.id)
        .values(status=EventRequestStatus.REJECTED)
    )
    on_event_row_lock(lambda connection: connection.execute(rejected))

    with pytest.raises(EventCancellationNotAllowedError) as exc_info:
        _cancel(db_session)

    assert exc_info.value.message.endswith("this one is rejected.")
    [saved] = change_requests_of(saved_event_request.id)
    assert saved.status is ChangeRequestStatus.PENDING

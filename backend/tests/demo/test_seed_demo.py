"""The demo seed fills an empty database for the walkthrough.

It creates one account per role, two client organisations, venues, equipment, and
events at every stage a demo needs: a draft, one waiting for the Lead, one under
review, one awaiting clarification, one being planned, one confirmed and open for
registration, one that has already taken place, and one rejected. Every step goes
through the modules' own services, so the data obeys the same rules a user's would.
It refuses to run on a database that already has an account.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.clock import local_today
from app.common.errors import ValidationError
from app.modules.auth.models import User
from app.modules.auth.permissions import Role
from app.modules.auth.services import authenticate_user, get_user_by_email
from app.modules.demo.services import (
    DEMO_ACCOUNTS,
    DemoDataExistsError,
    SeededEvent,
    seed_demo,
)
from app.modules.events.models import EventEquipmentLine, EventRequest, EventRequestStatus
from app.modules.events.services import complete_event_request, list_unassigned_requests
from app.modules.organisations.models import ClientOrganisation
from app.modules.registration.models import Registration
from app.modules.venue.services import list_pending_booking_requests

pytestmark = pytest.mark.demo

#: The stage each demo event is left at, as the walkthrough needs it.
EXPECTED_STAGES = {
    "Quarterly Town Hall": "draft",
    "Northwind Product Launch": "submitted",
    "Partner Summit": "under_review",
    "Data Science Workshop": "awaiting_clarification",
    "Charity Gala Luncheon": "approved",
    "Annual Tech Conference": "confirmed",
    "Leadership Breakfast": "confirmed",
    "Regional Roadshow": "rejected",
}


def _event(db_session: Session, name: str) -> EventRequest:
    """The seeded event called ``name``."""
    return db_session.scalars(select(EventRequest).where(EventRequest.name == name)).one()


def _count(db_session: Session, model: type) -> int:
    """How many rows of ``model`` are saved."""
    return db_session.scalar(select(func.count()).select_from(model))


@pytest.fixture()
def seed_day() -> date:
    """The day the seed runs; the events are dated around it."""
    return local_today()


@pytest.fixture()
def seeded(db_session: Session, seed_day: date, password: str) -> list[SeededEvent]:
    """The events the seed reports, after seeding an empty database."""
    return seed_demo(password, today=seed_day)


# --------------------------------------------------------------------------
# Accounts: one per role, all signing in with the password typed at the prompt
# --------------------------------------------------------------------------


def test_there_is_a_demo_account_for_every_role() -> None:
    roles = {account.role for account in DEMO_ACCOUNTS}

    assert roles == set(Role)


def test_every_demo_account_signs_in_with_the_chosen_password(
    seeded: list[SeededEvent], password: str
) -> None:
    for account in DEMO_ACCOUNTS:
        signed_in = authenticate_user(account.email, password).user

        assert (signed_in.full_name, signed_in.role) == (account.full_name, account.role)


def test_each_organiser_belongs_to_their_own_organisation(
    seeded: list[SeededEvent], db_session: Session
) -> None:
    organisations = db_session.scalars(select(ClientOrganisation)).all()
    names_by_id = {organisation.id: organisation.name for organisation in organisations}

    acme = get_user_by_email("olivia@acme.example")
    northwind = get_user_by_email("nadia@northwind.example")

    assert names_by_id[acme.organisation_id] == "Acme Events"
    assert names_by_id[northwind.organisation_id] == "Northwind Conferences"


# --------------------------------------------------------------------------
# Events: one at each stage of the walkthrough
# --------------------------------------------------------------------------


def test_each_event_is_saved_at_its_walkthrough_stage(
    seeded: list[SeededEvent], db_session: Session
) -> None:
    saved = db_session.scalars(select(EventRequest)).all()
    stages = {event.name: event.status.value for event in saved}

    assert stages == EXPECTED_STAGES


def test_the_seed_reports_every_event_with_its_reference_and_stage(
    seeded: list[SeededEvent], db_session: Session
) -> None:
    reported = {event.name: event.status for event in seeded}

    assert reported == EXPECTED_STAGES
    for event in seeded:
        assert _event(db_session, event.name).reference == event.reference


def test_events_are_dated_around_the_day_the_seed_runs(
    seeded: list[SeededEvent], db_session: Session, seed_day: date
) -> None:
    conference = _event(db_session, "Annual Tech Conference")
    breakfast = _event(db_session, "Leadership Breakfast")

    assert conference.proposed_date == seed_day + timedelta(days=14)
    assert breakfast.proposed_date == seed_day - timedelta(days=1)


def test_only_the_product_launch_waits_for_the_lead(seeded: list[SeededEvent]) -> None:
    queued = [event.name for event in list_unassigned_requests()]

    assert queued == ["Northwind Product Launch"]


def test_venue_staff_have_the_gala_booking_to_decide(seeded: list[SeededEvent]) -> None:
    pending = [shown.request.purpose for shown in list_pending_booking_requests()]

    assert pending == ["Charity Gala Luncheon"]


def test_technical_support_have_the_gala_microphones_to_review(
    seeded: list[SeededEvent], db_session: Session
) -> None:
    gala = _event(db_session, "Charity Gala Luncheon")
    unreviewed = db_session.scalars(
        select(EventEquipmentLine).where(EventEquipmentLine.provided_quantity.is_(None))
    ).all()

    assert [(line.event_request_id, line.quantity) for line in unreviewed] == [(gala.id, 4)]


def test_the_conference_is_open_for_registration_with_one_attendee(
    seeded: list[SeededEvent], db_session: Session
) -> None:
    conference = _event(db_session, "Annual Tech Conference")
    attendee = get_user_by_email("alex@example.com")

    [registration] = db_session.scalars(select(Registration)).all()

    assert (conference.registration_enabled, conference.registration_capacity) == (True, 100)
    assert (registration.event_request_id, registration.attendee_id) == (
        conference.id,
        attendee.id,
    )


def test_the_breakfast_has_ended_so_its_coordinator_can_mark_it_completed(
    seeded: list[SeededEvent], db_session: Session
) -> None:
    breakfast = _event(db_session, "Leadership Breakfast")
    coordinator = get_user_by_email("carl@connectsphere.example")

    completed = complete_event_request(coordinator.id, breakfast.reference)

    assert completed.status is EventRequestStatus.COMPLETED


# --------------------------------------------------------------------------
# Refusals: never on a database with accounts, never half-done on a bad password
# --------------------------------------------------------------------------


def test_a_database_with_an_account_is_refused_and_left_as_it_was(
    db_session: Session, make_user: Callable[..., User], password: str
) -> None:
    db_session.add(make_user())
    db_session.commit()

    with pytest.raises(DemoDataExistsError) as raised:
        seed_demo(password)

    assert raised.value.status_code == 409
    assert raised.value.error_code == "demo_data_exists"
    assert (_count(db_session, User), _count(db_session, ClientOrganisation)) == (1, 0)


def test_a_password_the_policy_refuses_saves_nothing(db_session: Session) -> None:
    with pytest.raises(ValidationError) as raised:
        seed_demo("short")

    assert set(raised.value.details) == {"password"}
    assert (_count(db_session, User), _count(db_session, ClientOrganisation)) == (0, 0)

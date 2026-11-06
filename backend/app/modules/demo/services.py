"""Seed an empty database with demo data for the walkthrough.

Everything is made through the other modules' services, in the order a user would
do it in the app: staff record the organisations, the organisers register, the Lead
assigns, the coordinator reviews, and so on. So the data passes the same validation,
and leaves the same history and notifications, as real use would.

The events are dated around the day the seed runs, so the data is current whenever
it is seeded. One event, the breakfast, took place yesterday. It is submitted as if
on the day before, since submission is the only step that refuses a past date, so
it can be marked completed in the demo (SCRUM-68).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Protocol

from app.common.clock import app_timezone, local_today
from app.common.errors import AppError
from app.modules.auth.permissions import INTERNAL_ROLES, Role
from app.modules.auth.services import create_staff_user, has_any_users, register_user
from app.modules.equipment.services import create_equipment_type, reserve_equipment
from app.modules.events.services import (
    add_equipment_line,
    assign_coordinator_to_request,
    confirm_event_request,
    decide_event_request,
    record_equipment_outcome,
    record_safety_outcome,
    request_clarification,
    save_draft_event_request,
    start_event_request_review,
    submit_event_request,
    submit_for_safety_review,
    update_registration_settings,
)
from app.modules.organisations.services import create_organisation
from app.modules.registration.services import register_for_event
from app.modules.venue.services import create_venue, decide_booking_request, raise_booking_request

DATABASE_NOT_EMPTY_MESSAGE = (
    "The database already has accounts, so no demo data was added. Seed only an empty "
    "database: reset it first with 'flask db downgrade base && flask db upgrade'."
)


@dataclass(frozen=True)
class DemoAccount:
    """One demo account: who it is, the role it signs in as, and its organisation."""

    full_name: str
    email: str
    role: Role
    organisation: str | None = None


@dataclass(frozen=True)
class SeededEvent:
    """One event the seed made, as the command lists it."""

    reference: str
    name: str
    status: str


class DemoDataExistsError(AppError):
    """The database already has accounts, so demo data isn't added (409)."""

    status_code = 409
    error_code = "demo_data_exists"


ACME = "Acme Events"
NORTHWIND = "Northwind Conferences"

OLIVIA = "olivia@acme.example"
NADIA = "nadia@northwind.example"
ALEX = "alex@example.com"
CARL = "carl@connectsphere.example"
CARA = "cara@connectsphere.example"
LEAH = "leah@connectsphere.example"
VERA = "vera@connectsphere.example"
TINA = "tina@connectsphere.example"
SAM = "sam@connectsphere.example"

#: Every demo account, one or more for each role.
DEMO_ACCOUNTS: tuple[DemoAccount, ...] = (
    DemoAccount("Carl Coordinator", CARL, Role.EVENT_COORDINATOR),
    DemoAccount("Cara Coordinator", CARA, Role.EVENT_COORDINATOR),
    DemoAccount("Leah Lead", LEAH, Role.EVENT_COORDINATOR_LEAD),
    DemoAccount("Vera Venue", VERA, Role.VENUE_STAFF),
    DemoAccount("Tina Technician", TINA, Role.TECHNICAL_SUPPORT_STAFF),
    DemoAccount("Sam Safety", SAM, Role.SAFETY_OFFICER),
    DemoAccount("Olivia Organiser", OLIVIA, Role.EVENT_ORGANISER, ACME),
    DemoAccount("Nadia Ng", NADIA, Role.EVENT_ORGANISER, NORTHWIND),
    DemoAccount("Alex Attendee", ALEX, Role.ATTENDEE),
    DemoAccount("Bella Attendee", "bella@example.com", Role.ATTENDEE),
)

ORGANISATIONS: tuple[dict[str, str], ...] = (
    {"name": ACME, "contact_name": "Olivia Organiser", "contact_email": OLIVIA},
    {"name": NORTHWIND, "contact_name": "Nadia Ng", "contact_email": NADIA},
)

MAIN_HALL = "Main Hall"
SEMINAR_ROOM = "Seminar Room 2-1"

#: Left without opening hours, each venue takes the default: 09:00 to 18:00 daily.
VENUES: tuple[dict[str, Any], ...] = (
    {
        "name": MAIN_HALL,
        "location": "Level 1, Block A",
        "capacity": 300,
        "supported_layouts": ["theatre", "banquet"],
        "facilities": ["projector", "stage", "sound system"],
        "accessibility_features": ["wheelchair access", "hearing loop"],
    },
    {
        "name": SEMINAR_ROOM,
        "location": "Level 2, Block B",
        "capacity": 40,
        "supported_layouts": ["classroom", "boardroom"],
        "facilities": ["whiteboard", "screen"],
        "accessibility_features": ["wheelchair access"],
    },
    {
        "name": "Rooftop Terrace",
        "location": "Level 8, Block A",
        "capacity": 120,
        "supported_layouts": ["banquet", "other"],
        "facilities": ["outdoor seating"],
        "accessibility_features": [],
    },
)

PROJECTOR = "Projector"
MICROPHONE = "Wireless microphone"

EQUIPMENT_TYPES: tuple[dict[str, Any], ...] = (
    {"name": PROJECTOR, "total_quantity": 10, "store_name": "Central AV store"},
    {"name": MICROPHONE, "total_quantity": 12, "store_name": "Central AV store"},
)

#: The Safety Officer's note on each of the seven checklist items (SCRUM-98 AC2).
SAFETY_CHECKLIST = {
    "attendance_vs_capacity": "Expected attendance is within the venue's capacity.",
    "venue_layout": "The layout keeps the aisles clear.",
    "emergency_access": "Two signed exits, both unobstructed.",
    "accessibility": "Step-free entrance confirmed.",
    "equipment_placement": "Cables are taped down away from walkways.",
    "crowd_movement": "One-way flow at the doors.",
    "venue_restrictions": "No open flames.",
}


@dataclass(frozen=True)
class _Setting:
    """What every event's setup needs: who is who, what can be booked, and when."""

    user_ids: dict[str, int]
    venue_ids: dict[str, int]
    equipment_ids: dict[str, int]
    today: date


# --------------------------------------------------------------------------
# The cast and the catalogue
# --------------------------------------------------------------------------


def _account_payload(account: DemoAccount, password: str) -> dict[str, Any]:
    """What signing ``account`` up sends, apart from any organisation."""
    return {
        "full_name": account.full_name,
        "email": account.email,
        "password": password,
        "role": account.role.value,
    }


class _Named(Protocol):
    """A record a create service returns: the seed keeps its id under its name."""

    id: int
    name: str


def _ids_by_name(
    payloads: tuple[dict[str, Any], ...], create: Callable[[dict[str, Any]], _Named]
) -> dict[str, int]:
    """Make one record per payload with ``create``; return each new id by its name."""
    ids: dict[str, int] = {}
    for payload in payloads:
        record = create(payload)
        ids[record.name] = record.id
    return ids


def _create_accounts(password: str) -> dict[str, int]:
    """Create every demo account; return each one's id by email.

    Staff are created first, as ``create-staff-user`` would (ADR-0023), so a password
    the policy refuses stops the seed before it has saved anything. Then the
    organisations are recorded, and the organisers and attendees sign up, each
    organiser into their own organisation (ADR-0013).
    """
    user_ids: dict[str, int] = {}
    for account in DEMO_ACCOUNTS:
        if account.role in INTERNAL_ROLES:
            staff = create_staff_user(_account_payload(account, password))
            user_ids[account.email] = staff.id

    organisation_ids = _ids_by_name(ORGANISATIONS, create_organisation)
    for account in DEMO_ACCOUNTS:
        if account.role in INTERNAL_ROLES:
            continue
        payload = _account_payload(account, password)
        if account.organisation is not None:
            payload["organisation_id"] = organisation_ids[account.organisation]
        user_ids[account.email] = register_user(payload).id
    return user_ids


# --------------------------------------------------------------------------
# The steps an event goes through, each taken by the person who takes it in the app
# --------------------------------------------------------------------------


def _event_details(name: str, purpose: str, day: date, hours: tuple[str, str]) -> dict[str, Any]:
    """A submission for ``name`` on ``day``, running for ``hours`` (start, end)."""
    start_time, end_time = hours
    return {
        "name": name,
        "purpose": purpose,
        "description": f"{name}: {purpose}",
        "proposed_date": day.isoformat(),
        "start_time": start_time,
        "end_time": end_time,
        "expected_attendance": 30,
    }


def _assign_and_review(setting: _Setting, reference: str, coordinator: str) -> None:
    """The Lead gives the request to ``coordinator``, who starts reviewing it."""
    assign_coordinator_to_request(
        reference, {"coordinator_email": coordinator}, assigned_by=setting.user_ids[LEAH]
    )
    start_event_request_review(setting.user_ids[coordinator], reference)


def _approve(setting: _Setting, reference: str, coordinator: str) -> None:
    """The coordinator approves the request (SCRUM-31)."""
    decide_event_request(setting.user_ids[coordinator], reference, {"outcome": "approved"})


def _at(day: date, clock_time: str) -> str:
    """``clock_time`` on ``day`` in business time, as the booking routes take it."""
    moment = datetime.combine(day, time.fromisoformat(clock_time), tzinfo=app_timezone())
    return moment.isoformat()


def _whole_event_booking(details: dict[str, Any], venue_id: int) -> dict[str, Any]:
    """A booking request for ``venue_id`` covering the event ``details`` describes."""
    day = date.fromisoformat(details["proposed_date"])
    return {
        "venue_id": venue_id,
        "starts_at": _at(day, details["start_time"]),
        "ends_at": _at(day, details["end_time"]),
        "purpose": details["name"],
    }


def _approve_booking(setting: _Setting, request_id: int) -> None:
    """Venue Staff approve the booking request (SCRUM-43)."""
    decide_booking_request(request_id, {"outcome": "approved"}, decided_by=setting.user_ids[VERA])


def _confirm(setting: _Setting, reference: str, coordinator: str) -> None:
    """Send it to Safety Review, the Safety Officer approves, and it is confirmed."""
    coordinator_id = setting.user_ids[coordinator]
    submit_for_safety_review(coordinator_id, reference)
    approval = {"outcome": "approved", "checklist": SAFETY_CHECKLIST}
    record_safety_outcome(setting.user_ids[SAM], reference, approval)
    confirm_event_request(coordinator_id, reference)


class _SavedEvent(Protocol):
    """What the seed reads back from an event a service returns."""

    reference: str
    name: str
    status: Enum


def _seeded(event: _SavedEvent) -> SeededEvent:
    """The command's summary line for ``event``, at the stage it was left at."""
    return SeededEvent(reference=event.reference, name=event.name, status=event.status.value)


# --------------------------------------------------------------------------
# One event at each stage of the walkthrough
# --------------------------------------------------------------------------


def _draft(setting: _Setting) -> SeededEvent:
    """A draft Olivia saved and hasn't submitted (SCRUM-20)."""
    details = {"name": "Quarterly Town Hall", "purpose": "Share the quarter's results."}
    return _seeded(save_draft_event_request(setting.user_ids[OLIVIA], details))


def _waiting_for_the_lead(setting: _Setting) -> SeededEvent:
    """Submitted by Nadia and not yet assigned: it is in the Lead's queue (SCRUM-95)."""
    day = setting.today + timedelta(days=21)
    details = _event_details(
        "Northwind Product Launch", "Launch the new product line.", day, ("10:00", "13:00")
    )
    return _seeded(submit_event_request(setting.user_ids[NADIA], details, today=setting.today))


def _under_review(setting: _Setting) -> SeededEvent:
    """Assigned to Carl, who has started reviewing it (SCRUM-31)."""
    day = setting.today + timedelta(days=28)
    details = _event_details(
        "Partner Summit", "Meet our partners for the year ahead.", day, ("09:00", "12:00")
    )
    submitted = submit_event_request(setting.user_ids[OLIVIA], details, today=setting.today)
    _assign_and_review(setting, submitted.reference, CARL)
    return _seeded(submitted)


def _awaiting_clarification(setting: _Setting) -> SeededEvent:
    """Carl has asked Nadia a question and is waiting for her answer (SCRUM-32)."""
    day = setting.today + timedelta(days=35)
    details = _event_details(
        "Data Science Workshop", "A hands-on workshop for analysts.", day, ("13:00", "17:00")
    )
    submitted = submit_event_request(setting.user_ids[NADIA], details, today=setting.today)
    _assign_and_review(setting, submitted.reference, CARL)
    question = {"message": "Will any participants need step-free access?"}
    asked = request_clarification(setting.user_ids[CARL], submitted.reference, question)
    return _seeded(asked)


def _being_planned(setting: _Setting) -> SeededEvent:
    """Approved, with a venue booking and an equipment line still to be decided.

    Venue Staff have the booking in their queue (SCRUM-43) and Technical Support the
    microphones in theirs (SCRUM-48).
    """
    day = setting.today + timedelta(days=42)
    details = _event_details(
        "Charity Gala Luncheon", "Raise funds for the children's ward.", day, ("11:00", "15:00")
    )
    submitted = submit_event_request(setting.user_ids[OLIVIA], details, today=setting.today)
    reference = submitted.reference
    _assign_and_review(setting, reference, CARA)
    _approve(setting, reference, CARA)

    booking = _whole_event_booking(details, setting.venue_ids[MAIN_HALL])
    raise_booking_request(reference, booking, requested_by=setting.user_ids[CARA])
    microphones = {
        "equipment_type_id": setting.equipment_ids[MICROPHONE],
        "quantity": 4,
        "notes": "Two for the stage, two for the floor.",
    }
    add_equipment_line(setting.user_ids[CARA], reference, microphones)
    return _seeded(submitted)


def _open_for_registration(setting: _Setting) -> SeededEvent:
    """Confirmed in two weeks' time, open for registration, with Alex registered.

    Its venue is booked and its projectors reserved, and the Safety Officer has
    approved it (SCRUM-49, SCRUM-69, SCRUM-52).
    """
    day = setting.today + timedelta(days=14)
    details = _event_details(
        "Annual Tech Conference",
        "Talks and demos on what we built this year.",
        day,
        ("09:00", "17:00"),
    )
    details["registration_required"] = True
    submitted = submit_event_request(setting.user_ids[OLIVIA], details, today=setting.today)
    reference = submitted.reference
    _assign_and_review(setting, reference, CARA)
    _approve(setting, reference, CARA)

    booking = _whole_event_booking(details, setting.venue_ids[MAIN_HALL])
    shown = raise_booking_request(reference, booking, requested_by=setting.user_ids[CARA])
    _approve_booking(setting, shown.request.id)

    projectors = {"equipment_type_id": setting.equipment_ids[PROJECTOR], "quantity": 2}
    line = add_equipment_line(setting.user_ids[CARA], reference, projectors)
    record_equipment_outcome(setting.user_ids[TINA], reference, line.id, {"provided_quantity": 2})
    reserve_equipment(reference, projectors, reserved_by=setting.user_ids[TINA])

    _confirm(setting, reference, CARA)
    registration = {"registration_enabled": True, "registration_capacity": 100}
    opened = update_registration_settings(setting.user_ids[CARA], reference, registration)
    register_for_event(setting.user_ids[ALEX], opened.id)
    return _seeded(opened)


def _already_held(setting: _Setting) -> SeededEvent:
    """Confirmed for yesterday, so Carl can mark it completed in the demo (SCRUM-68).

    It is submitted as if on the day before yesterday, since submission refuses a
    date in the past; nothing after that looks at the date.
    """
    day = setting.today - timedelta(days=1)
    details = _event_details(
        "Leadership Breakfast", "Breakfast with the leadership team.", day, ("10:00", "12:00")
    )
    submitted_on = day - timedelta(days=1)
    submitted = submit_event_request(setting.user_ids[NADIA], details, today=submitted_on)
    reference = submitted.reference
    _assign_and_review(setting, reference, CARL)
    _approve(setting, reference, CARL)

    booking = _whole_event_booking(details, setting.venue_ids[SEMINAR_ROOM])
    shown = raise_booking_request(reference, booking, requested_by=setting.user_ids[CARL])
    _approve_booking(setting, shown.request.id)
    _confirm(setting, reference, CARL)
    return _seeded(submitted)


def _rejected(setting: _Setting) -> SeededEvent:
    """Rejected by Carl, with his reason on the record (SCRUM-31)."""
    day = setting.today + timedelta(days=56)
    details = _event_details(
        "Regional Roadshow", "Visit five cities in one week.", day, ("09:00", "18:00")
    )
    submitted = submit_event_request(setting.user_ids[NADIA], details, today=setting.today)
    _assign_and_review(setting, submitted.reference, CARL)
    rejection = {"outcome": "rejected", "reason": "There is no budget for travel this quarter."}
    decided = decide_event_request(setting.user_ids[CARL], submitted.reference, rejection)
    return _seeded(decided)


# --------------------------------------------------------------------------
# The seed
# --------------------------------------------------------------------------


def seed_demo(password: str, *, today: date | None = None) -> list[SeededEvent]:
    """Fill an empty database with demo data for the walkthrough.

    Creates an account for every role, all signing in with ``password``, two client
    organisations, three venues, two equipment types, and one event at each stage:
    a draft, one waiting for the Lead, one under review, one awaiting clarification,
    one being planned, one confirmed and open for registration, one that took place
    yesterday, and one rejected.

    Args:
        password: The password every demo account signs in with.
        today: The day the events are dated around; defaults to today in the
            business timezone.

    Returns:
        Every event made, with its reference and the stage it was left at.

    Raises:
        DemoDataExistsError: 409 — the database already has an account.
        ValidationError: 400 — the password breaks the policy (nothing is saved).
    """
    if has_any_users():
        raise DemoDataExistsError(DATABASE_NOT_EMPTY_MESSAGE)

    setting = _Setting(
        user_ids=_create_accounts(password),
        venue_ids=_ids_by_name(VENUES, create_venue),
        equipment_ids=_ids_by_name(EQUIPMENT_TYPES, create_equipment_type),
        today=today if today is not None else local_today(),
    )
    return [
        _draft(setting),
        _waiting_for_the_lead(setting),
        _under_review(setting),
        _awaiting_clarification(setting),
        _being_planned(setting),
        _open_for_registration(setting),
        _already_held(setting),
        _rejected(setting),
    ]

"""Add the registration notification kinds.

Revision ID: 0057_add_registration_kinds
Revises: 0055_add_suggested_alternative
Create Date: 2026-10-31

SCRUM-62 "Be notified about changes, cancellations and registrations" (ADR-0125):

* ``notification_kind`` gains ``registration_confirmed`` and ``registration_withdrawn``,
  raised to an Attendee about their own registration (AC4), and ``attendee_registered``
  and ``attendee_withdrawn``, raised to the Organiser who submitted the event (AC3).

Revises 0055 (SCRUM-70), main's head when this was rebased, which changes no enum; 0054
(SCRUM-111) is the last to change ``notification_kind``. Open pull requests #167
(SCRUM-61) and #173 (SCRUM-57) each add a 0056 on 0055, so this is 0057, leaving a gap
as 0053 did after 0050, and whichever merges later re-chains: re-point
``down_revision`` at the head the others leave, and add any kinds they add to the
previous values below, in the order Postgres holds them. The values are added outside
the migration's transaction, with ``IF NOT EXISTS``, as 0049 and 0054 do. Downgrading
deletes the rows of the new values and rebuilds the type without them (lossy, like
0054's).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0057_add_registration_kinds"
down_revision = "0055_add_suggested_alternative"
branch_labels = None
depends_on = None

#: What migrations 0009-0055 left, in the order Postgres holds them. Downgrade rebuilds
#: ``notification_kind`` with just this.
PREVIOUS_NOTIFICATION_KIND_VALUES = (
    "event_request_submitted",
    "coordinator_assigned",
    "equipment_requested",
    "significant_change",
    "event_request_approved",
    "event_request_rejected",
    "clarification_requested",
    "clarification_answered",
    "request_assigned",
    "venue_booking_requested",
    "equipment_reserved",
    "request_queued_for_lead",
    "equipment_outcome_recorded",
    "venue_booking_approved",
    "venue_booking_rejected",
    "safety_review_requested",
    "safety_check_approved",
    "safety_check_rejected",
    "safety_changes_requested",
    "event_confirmed",
    "venue_hold_placed",
    "venue_hold_expiry_changed",
    "venue_hold_expiring",
    "venue_hold_expired",
    "alternative_venue_needed",
    "venue_booking_conflicting",
    "venue_available_again",
    "venue_booking_released",
    "safety_review_event_changed",
    "replacement_venue_approved",
    "venue_booking_reconfirmed",
    "change_request_raised",
    "change_request_withdrawn",
    "venue_booking_cancelled",
    "safety_review_venue_cancelled",
)

#: Added here (SCRUM-62 AC3, AC4, ADR-0125).
ADDED_NOTIFICATION_KIND_VALUES = (
    "registration_confirmed",
    "registration_withdrawn",
    "attendee_registered",
    "attendee_withdrawn",
)


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # additions run outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_NOTIFICATION_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )


def downgrade() -> None:
    # The rows holding a removed value go first. Postgres can't remove an enum value,
    # so the type is then rebuilt with its previous list and the column re-cast.
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    op.execute(sa.text("ALTER TYPE notification_kind RENAME TO notification_kind_old"))
    sa.Enum(*PREVIOUS_NOTIFICATION_KIND_VALUES, name="notification_kind").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE notifications ALTER COLUMN kind"
            " TYPE notification_kind USING kind::text::notification_kind"
        )
    )
    op.execute(sa.text("DROP TYPE notification_kind_old"))

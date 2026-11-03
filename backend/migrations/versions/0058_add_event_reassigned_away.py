"""Add the notice an Event Coordinator gets when their event is reassigned away.

Revision ID: 0058_add_event_reassigned_away
Revises: 0056_decide_change_requests
Create Date: 2026-11-02

SCRUM-28 AC1, SCRUM-96 and SCRUM-39 AC6 (ADR-0130): ``notification_kind`` gains
``event_reassigned_away``, the previous coordinator's notice when the Lead reassigns
their event. It used to be ``request_assigned``, the organiser's "a coordinator has been
assigned" notice, which the ACs now forbid for someone who lost the event.

Revises 0056 (SCRUM-57), main's head when this was written and the last migration to
change ``notification_kind``. Open pull requests #166 and #167 also add a migration
after 0056 (both numbered 0057), so whichever merges later re-points its
``down_revision`` at the head the others leave, and adds any kinds they gave
``notification_kind`` to the list below. The value is added outside the migration's
transaction, with ``IF NOT EXISTS``, as 0054 does. Downgrading is lossy: it deletes the
notices of this kind, then rebuilds the type without it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0058_add_event_reassigned_away"
down_revision = "0056_decide_change_requests"
branch_labels = None
depends_on = None

#: What migrations 0009-0056 left, in the order Postgres holds them. Downgrade rebuilds
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
    "change_request_approved",
    "change_request_rejected",
    "event_rescheduled",
)
#: Added here: the previous coordinator's notice.
ADDED_NOTIFICATION_KIND_VALUES = ("event_reassigned_away",)


def upgrade() -> None:
    # Postgres won't let a transaction use an enum value it added itself, so the
    # addition runs outside the migration's transaction: Alembic's documented approach.
    with op.get_context().autocommit_block():
        for value in ADDED_NOTIFICATION_KIND_VALUES:
            op.execute(
                sa.text("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS :value").bindparams(
                    value=value
                )
            )


def downgrade() -> None:
    # The rows holding the removed kind go first. Postgres can't remove an enum value,
    # so the type is then rebuilt with its previous list and the column re-cast. No
    # index or constraint refers to ``notifications.kind``, so nothing else needs
    # re-creating.
    for value in ADDED_NOTIFICATION_KIND_VALUES:
        op.execute(sa.text("DELETE FROM notifications WHERE kind = :value").bindparams(value=value))
    op.execute(sa.text("ALTER TYPE notification_kind RENAME TO notification_kind_old"))
    sa.Enum(*PREVIOUS_NOTIFICATION_KIND_VALUES, name="notification_kind").create(op.get_bind())
    op.execute(
        sa.text(
            "ALTER TABLE notifications ALTER COLUMN kind "
            "TYPE notification_kind USING kind::text::notification_kind"
        )
    )
    op.execute(sa.text("DROP TYPE notification_kind_old"))

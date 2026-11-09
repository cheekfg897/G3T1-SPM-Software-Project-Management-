"""Unit tests for migration 0058, the previous coordinator's notice (ADR-0130).

``notification_kind`` gains ``event_reassigned_away``: the notice an Event Coordinator
gets when the Lead reassigns their event to another coordinator (SCRUM-96, SCRUM-39
AC6). It has no link, as SCRUM-28 AC1 asks of a notice to someone who lost the event.
``flask db check`` doesn't compare enum members, so these tests check the migration's
value lists against the model and the migration below it, and render its SQL for
Postgres offline.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import pytest

from app.modules.notifications.services import NotificationKind

pytestmark = [pytest.mark.scrum_28, pytest.mark.scrum_96]

LoadMigration = Callable[[str], ModuleType]
RenderMigrationSql = Callable[[Callable[[], None]], str]
AssertInOrder = Callable[[str, list[str]], None]

MIGRATION = "0058_add_event_reassigned_away.py"
#: The last migration to change ``notification_kind`` before this one.
NOTIFICATION_KINDS_BELOW = "0056_add_change_request_decisions.py"


def test_it_follows_mains_head_when_it_was_written(load_migration: LoadMigration) -> None:
    migration = load_migration(MIGRATION)

    assert migration.down_revision == "0056_decide_change_requests"
    assert migration.revision == "0058_add_event_reassigned_away"
    # ``alembic_version`` holds at most 32 characters.
    assert len(migration.revision) <= 32


def test_the_previous_kinds_are_what_the_migrations_below_left(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    below = load_migration(NOTIFICATION_KINDS_BELOW)

    # In Postgres's order: each ADD VALUE appends.
    kinds_left = (*below.PREVIOUS_NOTIFICATION_KIND_VALUES, *below.ADDED_NOTIFICATION_KIND_VALUES)

    assert kinds_left == migration.PREVIOUS_NOTIFICATION_KIND_VALUES


def test_with_the_kind_added_the_type_holds_exactly_the_models_kinds(
    load_migration: LoadMigration,
) -> None:
    migration = load_migration(MIGRATION)
    previous = set(migration.PREVIOUS_NOTIFICATION_KIND_VALUES)
    added = set(migration.ADDED_NOTIFICATION_KIND_VALUES)

    assert migration.ADDED_NOTIFICATION_KIND_VALUES == ("event_reassigned_away",)
    assert previous | added == {kind.value for kind in NotificationKind}


def test_upgrade_adds_the_kind_outside_the_transaction(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    # Postgres won't let a transaction use an enum value it added, so the addition sits
    # between a COMMIT and a new BEGIN.
    expected_in_order = [
        "COMMIT",
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'event_reassigned_away'",
        "BEGIN",
    ]

    sql = render_migration_sql(migration.upgrade)

    assert_in_order(sql, expected_in_order)


def test_downgrade_deletes_those_notices_and_rebuilds_the_type_without_the_kind(
    load_migration: LoadMigration,
    render_migration_sql: RenderMigrationSql,
    assert_in_order: AssertInOrder,
) -> None:
    migration = load_migration(MIGRATION)
    expected_in_order = [
        "DELETE FROM notifications WHERE kind = 'event_reassigned_away'",
        "ALTER TYPE notification_kind RENAME TO notification_kind_old",
        "CREATE TYPE notification_kind AS ENUM ('event_request_submitted'",
        "'venue_booking_cancelled', 'safety_review_venue_cancelled', "
        "'change_request_approved', 'change_request_rejected', 'event_rescheduled')",
        "ALTER TABLE notifications ALTER COLUMN kind "
        "TYPE notification_kind USING kind::text::notification_kind",
        "DROP TYPE notification_kind_old",
    ]

    sql = render_migration_sql(migration.downgrade)

    assert_in_order(sql, expected_in_order)
    assert "'event_reassigned_away')" not in sql

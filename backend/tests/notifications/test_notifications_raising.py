"""Unit tests for SCRUM-28 "Receive notifications about my events": raising them.

Covers AC1 (a notification names the event, says what happened and when, and links to
the event) and AC2 (each recipient gets their own notification). The decisions behind
the shape (one row per recipient, a snapshot of the event, the link) are ADR-0015.

AC1's one exception, since 15 Oct: a notice to someone who has just lost access to the
event, such as the previous coordinator after a reassignment, has no link, and says it
was reassigned away rather than assigned (SCRUM-96, SCRUM-39 AC6, ADR-0130).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import MESSAGE_BY_KIND, NotificationSchema
from app.modules.notifications.services import EventSummary, NotificationKind, notify_users

pytestmark = pytest.mark.scrum_28

Notify = Callable[..., list[Notification]]
ReloadNotification = Callable[[int], Notification]


def _shown(kind: NotificationKind) -> dict[str, Any]:
    """An unread notification of ``kind`` about Partner Summit, as the API shows it."""
    notification = Notification(
        id=1,
        recipient_id=3,
        event_request_id=42,
        event_reference="EVR-AAAAAAAA",
        event_name="Partner Summit",
        kind=kind,
        created_at=datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc),
        read_at=None,
    )
    return NotificationSchema().dump(notification)


# --------------------------------------------------------------------------
# AC2 — each recipient gets their own copy
# --------------------------------------------------------------------------


def test_each_recipient_gets_a_copy_with_the_event_kind_and_time(
    notify: Notify, reload_notification: ReloadNotification
) -> None:
    notifications = notify(3, 5)

    saved = [reload_notification(notification.id) for notification in notifications]
    rows = [
        (
            notification.recipient_id,
            notification.event_request_id,
            notification.event_reference,
            notification.event_name,
            notification.kind,
            notification.created_at,
            notification.read_at,
        )
        for notification in saved
    ]
    raised_at = datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
    kind = NotificationKind.EVENT_REQUEST_SUBMITTED
    assert rows == [
        (3, 42, "EVR-AAAAAAAA", "Partner Summit", kind, raised_at, None),
        (5, 42, "EVR-AAAAAAAA", "Partner Summit", kind, raised_at, None),
    ]


def test_no_recipients_writes_and_commits_nothing(
    mock_session: MagicMock, event_summary: EventSummary
) -> None:
    notifications = notify_users(
        [], event_summary, NotificationKind.EVENT_REQUEST_SUBMITTED, session=mock_session
    )

    assert notifications == []
    mock_session.add_all.assert_not_called()
    mock_session.commit.assert_not_called()


def test_created_at_defaults_to_the_current_instant(
    notify: Notify, reload_notification: ReloadNotification
) -> None:
    before = datetime.now(timezone.utc)

    [notification] = notify(3, now=None)

    after = datetime.now(timezone.utc)
    assert before <= reload_notification(notification.id).created_at <= after


# --------------------------------------------------------------------------
# AC1 — a notification names the event, says what happened and when, and links to it
# --------------------------------------------------------------------------


def test_a_notification_names_the_event_says_what_happened_when_and_links_to_it() -> None:
    shown = _shown(NotificationKind.EVENT_REQUEST_SUBMITTED)

    assert shown == {
        "id": 1,
        "kind": "event_request_submitted",
        "message": "A new event request was submitted.",
        "event_reference": "EVR-AAAAAAAA",
        "event_name": "Partner Summit",
        "link": "/events/EVR-AAAAAAAA",
        "created_at": "2026-10-01T09:00:00+08:00",
        "read_at": None,
        "detail": None,
    }


@pytest.mark.parametrize("kind", list(NotificationKind), ids=lambda kind: kind.value)
def test_every_kind_has_a_message(kind: NotificationKind) -> None:
    assert MESSAGE_BY_KIND[kind] != ""


# --------------------------------------------------------------------------
# AC1's exception — a notice to someone who lost the event has no link (ADR-0130)
# --------------------------------------------------------------------------


@pytest.mark.scrum_39
@pytest.mark.scrum_96
def test_a_notice_to_the_previous_coordinator_says_it_was_reassigned_away_with_no_link() -> None:
    shown = _shown(NotificationKind.EVENT_REASSIGNED_AWAY)

    assert shown == {
        "id": 1,
        "kind": "event_reassigned_away",
        "message": (
            "This event has been reassigned to another Event Coordinator and is no longer yours."
        ),
        "event_reference": "EVR-AAAAAAAA",
        "event_name": "Partner Summit",
        "link": None,
        "created_at": "2026-10-01T09:00:00+08:00",
        "read_at": None,
        "detail": None,
    }


@pytest.mark.parametrize(
    "kind",
    [kind for kind in NotificationKind if kind is not NotificationKind.EVENT_REASSIGNED_AWAY],
    ids=lambda kind: kind.value,
)
def test_every_other_kind_links_to_the_event(kind: NotificationKind) -> None:
    assert _shown(kind)["link"] == "/events/EVR-AAAAAAAA"

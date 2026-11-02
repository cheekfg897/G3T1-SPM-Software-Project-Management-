import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
} from '@/features/notifications/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee } from './backend'
import { assignedEvent, LEAD } from './plannedEvent'

/** An id no notification has, so marking it read is a 404. */
const MISSING_NOTIFICATION_ID = 2_000_000_000

afterEach(() => sendRequestsAs(null))

describe('SCRUM-28 notifications against the backend', () => {
  it('gives a new user an empty list and an unread count of 0', async () => {
    await signInAsNewAttendee()

    await expect(fetchNotifications()).resolves.toEqual([])
    await expect(fetchUnreadCount()).resolves.toBe(0)
  })

  it('refuses the list, the count and marking read without a token', async () => {
    // Each call is made only when its turn comes. Starting all three at once leaves the
    // later rejections unattached while the first is awaited, which Node reports as an
    // unhandled rejection and fails the run even though every assertion passes.
    const calls = [
      () => fetchNotifications(),
      () => fetchUnreadCount(),
      () => markNotificationRead(1),
    ]

    for (const call of calls) {
      expect(await refusal(call())).toMatchObject({ status: 401, code: 'authentication_error' })
    }
  })

  it('answers 404 when marking a notification that does not exist', async () => {
    await signInAsNewAttendee()

    const error = await refusal(markNotificationRead(MISSING_NOTIFICATION_ID))

    expect(error.status).toBe(404)
  })

  it.skipIf(LEAD === null)(
    "lists the organiser's assignment notice with a link to the event, and marks it read",
    async () => {
      const event = await assignedEvent()
      await signInAs(event.organiser)

      const [notice] = await fetchNotifications()

      expect(notice).toMatchObject({
        kind: 'request_assigned',
        message: 'An Event Coordinator has been assigned to your event request.',
        event_reference: event.reference,
        event_name: event.name,
        link: `/events/${event.reference}`,
        read_at: null,
        detail: null,
      })
      const marked = await markNotificationRead(notice?.id ?? MISSING_NOTIFICATION_ID)
      expect(marked.read_at).not.toBeNull()
      await expect(fetchUnreadCount()).resolves.toBe(0)
    },
  )

  it.todo(
    'sends the coordinator an event was reassigned away from event_reassigned_away with a null link (needs a second Event Coordinator account to reassign to; the mock and the backend unit tests cover it, ADR-0130)',
  )
})

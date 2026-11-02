import {
  decideBookingRequest,
  fetchBookingRequests,
  placeBookingHold,
  raiseBookingRequest,
} from '@/features/booking/api'
import {
  decideChangeRequest,
  decideEventRequest,
  editEventRequest,
  fetchEventHistory,
  fetchEventRequest,
  raiseChangeRequest,
  sendToSafetyReview,
  withdrawChangeRequest,
} from '@/features/eventRequests/api'
import type {
  ChangeRequest,
  DecisionChoice,
  EventRequest,
  RequestedChange,
} from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { addChangeRequest } from './changeRequestStore'

/**
 * The mock of the coordinator's decision on a change request
 * (POST .../<reference>/change-requests/<id>/decide), pinned to what the backend does (SCRUM-57,
 * ADR-0127): approving applies the values asked for, each in the history as the coordinator's
 * change, unless a field has moved since; rejecting needs a reason and changes nothing; the
 * request keeps who decided it, when and why; and while one is Pending, the event's own
 * decisions are refused (AC9). An approved change reassesses what it unsettles, as an edit does
 * (SCRUM-58, ADR-0129). The mock's "now" is 5 Oct, 12:00 pm.
 */

/** Omar's, under review and coordinated by Chloe: 12 Nov, 9:00 am to 5:00 pm, 250 expected. */
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
/** Also Chloe's, so only the event in the path can tell its requests from the Summit's. */
const CHLOES_OTHER_EVENT = 'EVR-B6YF2K8V'
/** Hana's, approved, and in Safety Review ready to confirm. */
const APPROVED_WITH_GAPS = 'EVR-PLAN0001'
const READY_TO_CONFIRM = 'EVR-PLAN0003'
const MOCK_NOW = '2026-10-05T12:00:00+08:00'
const CHLOE = MOCK_ACCOUNTS.coordinator
const LATER_AND_BIGGER = {
  start_time: '10:00',
  expected_attendance: 300,
  reason: 'The keynote speaker lands later.',
}
const APPROVE: DecisionChoice = { outcome: 'approved' }
const PENDING_MESSAGE =
  'The organiser has a change request waiting for your decision. Decide the change request first.'
const HANA = MOCK_ACCOUNTS.planningCoordinator
/** Hana's, approved and settled; nothing the mock starts with is both hers and rejected. */
const REJECTED_BY_HANA = 'EVR-PLAN0002'
/** The event's own decisions AC9 holds up, and the status each leaves it in when it goes ahead. */
const EVENT_DECISIONS = [
  {
    action: 'approving or rejecting it',
    coordinator: CHLOE,
    reference: PARTNER_SUMMIT,
    route: 'decide',
    body: { outcome: 'approved' },
    statusAfter: 'approved',
  },
  {
    action: 'rejecting it in planning',
    coordinator: HANA,
    reference: APPROVED_WITH_GAPS,
    route: 'reject',
    body: { reason: 'Out of budget.' },
    statusAfter: 'rejected',
  },
  {
    action: 'confirming it',
    coordinator: HANA,
    reference: READY_TO_CONFIRM,
    route: 'confirm',
    body: undefined,
    statusAfter: 'confirmed',
  },
]
/** Chloe's: approved, and Confirmed with no planning of its own; 9:00 am to 5:00 pm, 80 expected. */
const CAREERS_FAIR = 'EVR-BOOK0101'
const TOWN_HALL = 'EVR-BOOK0102'
const TIMING_REASON = "The event's date or time changed."
const LATER_START: RequestedChange = {
  field: 'start_time',
  previous_value: '09:00:00',
  requested_value: '10:00:00',
}
const FEWER_PEOPLE: RequestedChange = {
  field: 'expected_attendance',
  previous_value: 80,
  requested_value: 60,
}
const NEW_PROGRAMME: RequestedChange = {
  field: 'programme_notes',
  previous_value: null,
  requested_value: 'A panel is added.',
}

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

/** Omar raises this change to the Partner Summit; Chloe is then signed in. Answers its id. */
async function raisedOnTheSummit(
  change: Parameters<typeof raiseChangeRequest>[1] = LATER_AND_BIGGER,
): Promise<number> {
  signInAs(MOCK_ACCOUNTS.organiser)
  const raised = await raiseChangeRequest(PARTNER_SUMMIT, change)
  signInAs(CHLOE)
  return raised.id
}

/** Chloe approves the Summit: before that, she can't edit it directly (SCRUM-110). */
async function summitApproved() {
  signInAs(CHLOE)
  await decideEventRequest(PARTNER_SUMMIT, APPROVE)
}

/**
 * A change request kept on `reference` as if its organiser had raised it, Pending unless `kept`
 * says otherwise. Answers its id.
 */
function keptOn(reference: string, kept: Partial<ChangeRequest> = {}): number {
  const { id } = addChangeRequest(reference, {
    status: 'pending',
    changes: [{ field: 'expected_attendance', previous_value: 250, requested_value: 300 }],
    reason: 'More partners.',
    raised_by: 'Omar Rahman',
    raised_at: MOCK_NOW,
    withdrawn_at: null,
    withdrawal_note: null,
    decided_by: null,
    decided_at: null,
    decision_reason: null,
    ...kept,
  })
  return id
}

/** The stale refusal, naming this one field as the backend words it. */
function staleMessage(fieldThenAndNow: string): string {
  return (
    "This change request can't be approved because the event has changed since it was " +
    `raised. ${fieldThenAndNow} Reject it, and the organiser can raise a new one.`
  )
}

/** POST one of the event's own decisions, as the coordinator signed in. */
function postDecision(reference: string, route: string, body: object | undefined) {
  return apiRequest<EventRequest>(`/api/events/requests/${reference}/${route}`, {
    method: 'POST',
    body,
  })
}

describe('SCRUM-57 mock of approving a change request', () => {
  it('applies each value, records it as the coordinator, and keeps who decided it', async () => {
    const id = await raisedOnTheSummit()

    const approved = await decideChangeRequest(PARTNER_SUMMIT, id, {
      outcome: 'approved',
      reason: ' The hall holds 300. ',
    })

    expect(approved).toMatchObject({
      id,
      status: 'approved',
      decided_by: CHLOE.full_name,
      decided_at: MOCK_NOW,
      decision_reason: 'The hall holds 300.',
    })
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record).toMatchObject({ start_time: '10:00:00', expected_attendance: 300 })
    expect(record.change_requests).toEqual([approved])
    const { history } = await fetchEventHistory(PARTNER_SUMMIT)
    const applied = history.slice(-2).map((entry) => [entry.actor_name, entry.details.field])
    expect(applied).toEqual([
      [CHLOE.full_name, 'start_time'],
      [CHLOE.full_name, 'expected_attendance'],
    ])
  })

  it('refuses a request a field has moved away from, naming it then and now, and keeps it Pending', async () => {
    await summitApproved()
    const id = await raisedOnTheSummit()
    await editEventRequest(PARTNER_SUMMIT, { expected_attendance: 200 })

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_stale',
      message: staleMessage('Expected attendance: 250 when the change was requested, 200 now.'),
    })
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record.change_requests[0]?.status).toBe('pending')
    expect(record.start_time).toBe('09:00:00')
  })

  it.each([
    {
      said: 'a time to the minute',
      asked: { start_time: '10:00' },
      edit: { start_time: '08:30' },
      fieldThenAndNow: 'Start time: 09:00 when the change was requested, 08:30 now.',
    },
    {
      said: 'a field with no value as blank',
      asked: { programme_notes: 'Keynote at two.' },
      edit: { programme_notes: '' },
      fieldThenAndNow:
        'Programme notes: Keynote at 9:30, breakout rooms after lunch. when the change was ' +
        'requested, blank now.',
    },
  ])('says $said in the stale refusal', async ({ asked, edit, fieldThenAndNow }) => {
    await summitApproved()
    const id = await raisedOnTheSummit({ ...asked, reason: 'Plans have changed.' })
    await editEventRequest(PARTNER_SUMMIT, edit)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({ status: 409, message: staleMessage(fieldThenAndNow) })
  })

  it('refuses a value that would end the event before it starts, on its field', async () => {
    await summitApproved()
    const id = await raisedOnTheSummit({ end_time: '12:00', reason: 'The hall closes at noon.' })
    await editEventRequest(PARTNER_SUMMIT, { start_time: '13:00' })

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Invalid request.',
      fieldErrors: { end_time: ['Event must end after it starts.'] },
    })
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record.change_requests[0]?.status).toBe('pending')
    expect(record.end_time).toBe('17:00:00')
  })

  it('refuses a date that has passed since the request was raised, on its field', async () => {
    const id = keptOn(PARTNER_SUMMIT, {
      changes: [
        { field: 'proposed_date', previous_value: '2026-11-12', requested_value: '2026-10-04' },
      ],
    })
    signInAs(CHLOE)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { proposed_date: ['Proposed date cannot be in the past.'] },
    })
  })
})

describe('SCRUM-57 mock of a change request on an event that is over', () => {
  beforeEach(async () => {
    signInAs(HANA)
    await postDecision(REJECTED_BY_HANA, 'reject', { reason: 'Out of budget.' })
  })

  it.each([
    { status: 'completed', reference: 'EVR-PLAN0007' },
    { status: 'cancelled', reference: 'EVR-PLAN0008' },
    { status: 'rejected', reference: REJECTED_BY_HANA },
  ])(
    'refuses to apply it to a $status event, and it can still be rejected',
    async ({ status, reference }) => {
      const id = keptOn(reference)

      const refused = await refusal(decideChangeRequest(reference, id, APPROVE))
      const rejected = await decideChangeRequest(reference, id, {
        outcome: 'rejected',
        reason: 'The event is over.',
      })

      expect(refused).toMatchObject({
        status: 409,
        code: 'change_request_not_allowed',
        message: `A change can't be applied to a ${status} event. Reject the change request instead.`,
      })
      expect(rejected.status).toBe('rejected')
    },
  )
})

describe('SCRUM-57 mock of rejecting a change request', () => {
  it('needs a reason, under its field', async () => {
    const id = await raisedOnTheSummit()

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, { outcome: 'rejected' }))

    expect(refused).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { reason: ['Say why the change request is rejected.'] },
    })
  })

  it('keeps the reason and leaves the event as it was', async () => {
    const id = await raisedOnTheSummit()

    const rejected = await decideChangeRequest(PARTNER_SUMMIT, id, {
      outcome: 'rejected',
      reason: 'The hall holds 250.',
    })

    expect(rejected).toMatchObject({ status: 'rejected', decision_reason: 'The hall holds 250.' })
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record).toMatchObject({ start_time: '09:00:00', expected_attendance: 250 })
  })
})

describe("SCRUM-57 mock's refusals", () => {
  it('refuses deciding one that is no longer Pending, naming its status (AC5)', async () => {
    const id = await raisedOnTheSummit()
    signInAs(MOCK_ACCOUNTS.organiser)
    await withdrawChangeRequest(PARTNER_SUMMIT, id)
    signInAs(CHLOE)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_not_pending',
      message: 'Only a pending change request can be decided; this one is withdrawn.',
    })
  })

  it('answers not found for an id the event does not have', async () => {
    signInAs(CHLOE)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, 999, APPROVE))

    expect(refused).toMatchObject({ status: 404, code: 'not_found' })
  })

  it("answers not found for the id of another event's request, leaving it Pending", async () => {
    const decoy = keptOn(CHLOES_OTHER_EVENT)
    signInAs(CHLOE)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, decoy, APPROVE))

    expect(refused).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Change request not found.',
    })
    const record = await fetchEventRequest(CHLOES_OTHER_EVENT)
    expect(record.change_requests[0]?.status).toBe('pending')
  })

  it('answers not found to a coordinator the event is not assigned to, leaving it Pending', async () => {
    const id = await raisedOnTheSummit()
    signInAs(MOCK_ACCOUNTS.freshCoordinator)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Event request not found.',
    })
    signInAs(CHLOE)
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record.change_requests[0]?.status).toBe('pending')
  })

  it('refuses the organiser by role', async () => {
    const id = await raisedOnTheSummit()
    signInAs(MOCK_ACCOUNTS.organiser)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({ status: 403, code: 'authorization_error' })
  })
})

describe('SCRUM-58 mock of what an approved change reassesses', () => {
  const RISE_TO_90 =
    "The event's expected attendance rose from 80 to 90, above this arrangement's expected occupancy of 80."

  /** Chloe raises a booking for all 80 on the careers fair, in the hall (venue 1, for 200). */
  function raiseOnCareersFair() {
    signInAs(CHLOE)
    return raiseBookingRequest(CAREERS_FAIR, {
      venue_id: 1,
      purpose: 'Hall',
      starts_at: '2026-11-10T09:00:00+08:00',
      ends_at: '2026-11-10T12:00:00+08:00',
    })
  }

  /** The event's coordinator, already signed in, approves a change of its attendance. */
  function approveAttendance(reference: string, from: number, to: number) {
    const id = keptOn(reference, {
      changes: [{ field: 'expected_attendance', previous_value: from, requested_value: to }],
    })
    return decideChangeRequest(reference, id, APPROVE)
  }

  /** Chloe raises a smaller room for `occupancy` of them on the careers fair (venue 2). */
  function raiseSmallerRoom(occupancy: number) {
    signInAs(CHLOE)
    return raiseBookingRequest(CAREERS_FAIR, {
      venue_id: 2,
      purpose: 'Workshop',
      starts_at: '2026-11-10T13:00:00+08:00',
      ends_at: '2026-11-10T15:00:00+08:00',
      expected_occupancy: occupancy,
    })
  }

  /** Venue Staff hold the hall, for all 80, on a two-venue event; Chloe is then signed in. */
  async function holdTheHall() {
    const hall = await raiseOnCareersFair()
    const room = await raiseSmallerRoom(10)
    signInAs(MOCK_ACCOUNTS.venueStaff)
    await placeBookingHold(hall.id, { expires_at: '2026-10-20T17:00:00+08:00' })
    signInAs(CHLOE)
    return { hallId: hall.id, roomId: room.id }
  }

  async function flagsOn(bookingId: number) {
    const bookings = await fetchBookingRequests(CAREERS_FAIR)
    return bookings.find((booking) => booking.id === bookingId)?.reassessment_flags
  }

  it('flags the booking and shows it on the record (AC1)', async () => {
    const hall = await raiseOnCareersFair()
    const id = keptOn(CAREERS_FAIR, { changes: [LATER_START] })

    await decideChangeRequest(CAREERS_FAIR, id, APPROVE)

    const flags = [{ kind: 'requires_reconfirmation', reason: TIMING_REASON }]
    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking).toMatchObject({ id: hall.id, flagged_after_change: true })
    expect(booking?.reassessment_flags).toEqual(flags)
    const record = await fetchEventRequest(CAREERS_FAIR)
    expect(record.venue_arrangements?.[0]?.reassessment_flags).toEqual(flags)
  })

  it('leaves the booking untouched when anything else changes (AC4)', async () => {
    await raiseOnCareersFair()
    const id = keptOn(CAREERS_FAIR, { changes: [NEW_PROGRAMME] })

    await decideChangeRequest(CAREERS_FAIR, id, APPROVE)

    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking).toMatchObject({ flagged_after_change: false, reassessment_flags: [] })
  })

  it('leaves the booking untouched when the change is rejected', async () => {
    await raiseOnCareersFair()
    const id = keptOn(CAREERS_FAIR, { changes: [LATER_START] })

    await decideChangeRequest(CAREERS_FAIR, id, { outcome: 'rejected', reason: 'No.' })

    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking).toMatchObject({ flagged_after_change: false, reassessment_flags: [] })
  })

  it('marks a booking an earlier rise outgrew when the attendance rises again (AC2)', async () => {
    await raiseOnCareersFair()

    await approveAttendance(CAREERS_FAIR, 80, 90)
    await approveAttendance(CAREERS_FAIR, 90, 250)

    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking?.reassessment_flags).toEqual([
      { kind: 'requires_reconfirmation', reason: RISE_TO_90 },
      {
        kind: 'no_longer_suitable',
        reason: "Expected attendance of 250 exceeds the venue's capacity of 200.",
      },
    ])
  })

  it('marks a smaller room on a rise after the attendance fell below it (ADR-0094)', async () => {
    const room = await raiseSmallerRoom(15)

    await approveAttendance(CAREERS_FAIR, 80, 10)
    await approveAttendance(CAREERS_FAIR, 10, 18)

    expect(await flagsOn(room.id)).toEqual([
      {
        kind: 'requires_reconfirmation',
        reason:
          "The event's expected attendance rose from 10 to 18, above this arrangement's expected occupancy of 15.",
      },
    ])
  })

  it('leaves a booking On Hold unmarked (ADR-0129 decision 10)', async () => {
    const { hallId, roomId } = await holdTheHall()
    const id = keptOn(CAREERS_FAIR, { changes: [LATER_START] })

    await decideChangeRequest(CAREERS_FAIR, id, APPROVE)

    expect(await flagsOn(hallId)).toEqual([])
    expect(await flagsOn(roomId)).toEqual([
      { kind: 'requires_reconfirmation', reason: TIMING_REASON },
    ])
  })

  it('judges a hold approved later from when it was raised, as the backend reads the history', async () => {
    const { hallId } = await holdTheHall()
    await approveAttendance(CAREERS_FAIR, 80, 90)
    signInAs(MOCK_ACCOUNTS.venueStaff)
    await decideBookingRequest(hallId, { outcome: 'approved' })
    signInAs(CHLOE)

    await approveAttendance(CAREERS_FAIR, 90, 250)

    expect(await flagsOn(hallId)).toEqual([
      {
        kind: 'no_longer_suitable',
        reason: "Expected attendance of 250 exceeds the venue's capacity of 200.",
      },
    ])
  })

  it('adds nothing when the attendance falls after a rise (AC5)', async () => {
    await raiseOnCareersFair()

    await approveAttendance(CAREERS_FAIR, 80, 90)
    await approveAttendance(CAREERS_FAIR, 90, 85)

    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking?.reassessment_flags).toEqual([
      { kind: 'requires_reconfirmation', reason: RISE_TO_90 },
    ])
  })

  it('marks an arrangement the gates count on a second rise, naming the capacity (AC2)', async () => {
    signInAs(HANA)

    await approveAttendance(READY_TO_CONFIRM, 150, 160)
    await approveAttendance(READY_TO_CONFIRM, 160, 250)

    const refused = await refusal(sendToSafetyReview(READY_TO_CONFIRM))
    expect(refused).toMatchObject({
      fieldErrors: {
        venue_arrangements: [
          "Venue arrangement 46 is flagged (requires reconfirmation): The event's expected attendance rose from 150 to 160, above this arrangement's expected occupancy of 150.",
          "Venue arrangement 46 is flagged (no longer suitable): Expected attendance of 250 exceeds the venue's capacity of 200.",
        ],
      },
    })
  })

  it('holds the event back from Safety Review, naming the capacity (AC2, AC3)', async () => {
    signInAs(HANA)
    const id = keptOn(READY_TO_CONFIRM, {
      changes: [{ field: 'expected_attendance', previous_value: 150, requested_value: 250 }],
    })

    await decideChangeRequest(READY_TO_CONFIRM, id, APPROVE)

    const refused = await refusal(sendToSafetyReview(READY_TO_CONFIRM))
    expect(refused).toMatchObject({
      fieldErrors: {
        venue_arrangements: [
          "Venue arrangement 46 is flagged (no longer suitable): Expected attendance of 250 exceeds the venue's capacity of 200.",
        ],
      },
    })
  })

  it('withdraws a safety approval and sends the event back to Approved (AC6)', async () => {
    signInAs(HANA)
    const id = keptOn(READY_TO_CONFIRM, {
      changes: [{ field: 'start_time', previous_value: '10:00:00', requested_value: '11:00:00' }],
    })

    await decideChangeRequest(READY_TO_CONFIRM, id, APPROVE)

    const record = await fetchEventRequest(READY_TO_CONFIRM)
    expect(record.status).toBe('approved')
    const { history } = await fetchEventHistory(READY_TO_CONFIRM)
    expect(history.at(-1)).toMatchObject({
      kind: 'safety_approval_withdrawn',
      actor_name: HANA.full_name,
      details: { significant_fields: ['start_time'] },
    })
  })

  it('sends a Confirmed event back to Approved after any significant change (AC7)', async () => {
    signInAs(CHLOE)
    const id = keptOn(TOWN_HALL, { changes: [FEWER_PEOPLE] })

    await decideChangeRequest(TOWN_HALL, id, APPROVE)

    const record = await fetchEventRequest(TOWN_HALL)
    expect(record.status).toBe('approved')
  })

  it('leaves a Confirmed event Confirmed after a change that is not significant (AC7)', async () => {
    signInAs(CHLOE)
    const id = keptOn(TOWN_HALL, { changes: [NEW_PROGRAMME] })

    await decideChangeRequest(TOWN_HALL, id, APPROVE)

    const record = await fetchEventRequest(TOWN_HALL)
    expect(record.status).toBe('confirmed')
    const { history } = await fetchEventHistory(TOWN_HALL)
    const kinds = history.map((entry) => entry.kind)
    expect(kinds).not.toContain('safety_approval_withdrawn')
  })
})

describe("SCRUM-57 AC9 mock of the event's decisions waiting for a Pending change request", () => {
  it.each(EVENT_DECISIONS)('refuses $action', async ({ coordinator, reference, route, body }) => {
    keptOn(reference)
    signInAs(coordinator)

    const refused = await refusal(postDecision(reference, route, body))

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_pending',
      message: PENDING_MESSAGE,
    })
  })

  describe.each(['approved', 'rejected', 'withdrawn'] as const)(
    'with the only request %s',
    (status) => {
      it.each(EVENT_DECISIONS)(
        'goes ahead with $action',
        async ({ coordinator, reference, route, body, statusAfter }) => {
          keptOn(reference, { status })
          signInAs(coordinator)

          const decided = await postDecision(reference, route, body)

          expect(decided.status).toBe(statusAfter)
        },
      )
    },
  )
})

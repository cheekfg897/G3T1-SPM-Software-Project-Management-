import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'

import {
  canRequestChange,
  describeAgainstNow,
  describeRequestedChange,
  requestedChange,
} from './changeRequest'
import { formWith, RECORD } from './test/recordForm'

/**
 * SCRUM-56 AC2: what the organiser's change request form sends, and how a requested change is
 * worded on the record. Only the event's date, times, attendance, venue and equipment
 * requirements and programme notes can be asked for, and only those that differ from the record
 * are sent, with why (ADR-0126).
 */

describe('SCRUM-56 AC2 what the change request form sends', () => {
  it('sends only why when nothing was changed, for the backend to say what is missing', () => {
    const form = formWith({ reason: 'Our keynote speaker lands late.' })

    expect(requestedChange(form, RECORD)).toEqual({ reason: 'Our keynote speaker lands late.' })
  })

  it('sends each requestable field that changed, the attendance as a number', () => {
    const form = formWith({
      reason: 'More partners said yes.',
      proposed_date: '2026-11-19',
      start_time: '10:00',
      expected_attendance: '300',
      venue_requirements: 'A main hall for 300.',
      equipment_requirements: 'Two more microphones.',
      programme_notes: 'Keynote at 10:30.',
    })

    expect(requestedChange(form, RECORD)).toEqual({
      reason: 'More partners said yes.',
      proposed_date: '2026-11-19',
      start_time: '10:00',
      expected_attendance: 300,
      venue_requirements: 'A main hall for 300.',
      equipment_requirements: 'Two more microphones.',
      programme_notes: 'Keynote at 10:30.',
    })
  })

  it('sends an emptied requirement as null, asking for it to be cleared', () => {
    const form = formWith({ reason: 'We bring our own.', venue_requirements: '' })

    expect(requestedChange(form, RECORD)).toEqual({
      reason: 'We bring our own.',
      venue_requirements: null,
    })
  })

  it('never sends a detail a change request cannot ask for, even when it differs', () => {
    const form = formWith({ reason: 'Why not.', description: 'New words.', end_date: '2026-11-13' })

    expect(requestedChange(form, RECORD)).toEqual({ reason: 'Why not.', end_date: '2026-11-13' })
  })
})

describe('SCRUM-56 AC4 a requested change in words', () => {
  it('names the field and shows its value when raised beside the one asked for', () => {
    const change = { field: 'start_time', previous_value: '09:00:00', requested_value: '10:30:00' }

    expect(describeRequestedChange(change)).toEqual({
      label: 'Start time',
      value: '9:00 am → 10:30 am',
    })
  })

  it('says a value was not set, either side', () => {
    const added = { field: 'equipment_requirements', previous_value: null, requested_value: 'Mics' }
    const cleared = { field: 'programme_notes', previous_value: 'Keynote', requested_value: null }

    expect(describeRequestedChange(added)).toEqual({
      label: 'Equipment requirements',
      value: 'Not set → Mics',
    })
    expect(describeRequestedChange(cleared)).toEqual({
      label: 'Programme notes',
      value: 'Keynote → Not set',
    })
  })

  it('shows a date as a day and an attendance as its number', () => {
    const moved = {
      field: 'proposed_date',
      previous_value: '2026-11-12',
      requested_value: '2026-11-19',
    }
    const grown = { field: 'expected_attendance', previous_value: 250, requested_value: 300 }

    expect(describeRequestedChange(moved).value).toBe('Thu, 12 Nov → Thu, 19 Nov')
    expect(describeRequestedChange(grown)).toEqual({
      label: 'Expected attendance',
      value: '250 → 300',
    })
  })
})

describe('SCRUM-57 AC1 a requested change beside what the event holds now', () => {
  it("shows the event's value now, not the one when the request was raised", () => {
    const change = { field: 'expected_attendance', previous_value: 200, requested_value: 300 }

    expect(describeAgainstNow(change, { ...RECORD, expected_attendance: 250 })).toEqual({
      label: 'Expected attendance',
      value: '250 now → 300',
    })
  })

  it('shows a field the event holds nothing for as not set', () => {
    const change = {
      field: 'venue_requirements',
      previous_value: null,
      requested_value: 'Two rooms',
    }

    expect(describeAgainstNow(change, { ...RECORD, venue_requirements: null })).toEqual({
      label: 'Venue requirements',
      value: 'Not set now → Two rooms',
    })
  })

  it('shows a field a change request cannot ask for as not set now', () => {
    const change = { field: 'name', previous_value: 'Old', requested_value: 'New' }

    expect(describeAgainstNow(change, RECORD).value).toBe('Not set now → New')
  })
})

/**
 * SCRUM-56 AC1, AC6: who is offered a change request, as the page offers the form and the cancel
 * confirmation offers it instead (SCRUM-61, ADR-0122): the organiser, from Submitted to
 * Confirmed. The statuses are written out, and the others built from the list of them.
 */
describe('SCRUM-56 AC1, AC6 who may request a change', () => {
  const REQUESTABLE: EventRequestStatus[] = [
    EVENT_REQUEST_STATUS.SUBMITTED,
    EVENT_REQUEST_STATUS.UNDER_REVIEW,
    EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
    EVENT_REQUEST_STATUS.APPROVED,
    EVENT_REQUEST_STATUS.SAFETY_REVIEW,
    EVENT_REQUEST_STATUS.CONFIRMED,
  ]
  const NOT_REQUESTABLE = Object.values(EVENT_REQUEST_STATUS).filter(
    (status) => !REQUESTABLE.includes(status),
  )
  const NOT_ORGANISERS = Object.values(ROLE).filter((role) => role !== ROLE.EVENT_ORGANISER)

  function viewerWith(role: Role) {
    return { id: 1, full_name: 'Omar Rahman', role }
  }

  it.each(REQUESTABLE)('offers it to the organiser of an event that is %s', (status) => {
    expect(canRequestChange(viewerWith(ROLE.EVENT_ORGANISER), { ...RECORD, status })).toBe(true)
  })

  it.each(NOT_REQUESTABLE)('offers nothing on an event that is %s', (status) => {
    expect(canRequestChange(viewerWith(ROLE.EVENT_ORGANISER), { ...RECORD, status })).toBe(false)
  })

  it.each(NOT_ORGANISERS)('offers nothing to %s', (role) => {
    expect(canRequestChange(viewerWith(role), RECORD)).toBe(false)
  })

  it('offers nothing to someone signed out', () => {
    expect(canRequestChange(null, RECORD)).toBe(false)
  })
})

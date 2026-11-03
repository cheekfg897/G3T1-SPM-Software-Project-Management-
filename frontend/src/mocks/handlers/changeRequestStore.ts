import type { ChangeRequest } from '@/features/eventRequests/api'

import { errorResponse } from '../responses'

import { MOCK_NOW } from './catalogueFixtures'

/**
 * Each event's change requests as they stand, oldest first (SCRUM-56, ADR-0126): what the
 * change request routes keep (changeRequests.ts) and the event's record shows
 * (eventRequests.ts). Kept apart from both, so neither imports the other. None to start with.
 */

/** What a change request withdrawn by its event's cancellation says (SCRUM-56 AC9). */
const CANCELLED_WITHDRAWAL_NOTE = 'Withdrawn because the event was cancelled.'

let storedChangeRequests: Record<string, ChangeRequest[]> = {}
let lastId = 0

/** Forget every change request. Runs after every test. */
export function resetMockChangeRequests(): void {
  storedChangeRequests = {}
  lastId = 0
}

/** The event's change requests, oldest first. */
export function changeRequestsOf(reference: string): ChangeRequest[] {
  return storedChangeRequests[reference] ?? []
}

/** Keep a new change request on the event, with the next id; answers it as kept. */
export function addChangeRequest(
  reference: string,
  changeRequest: Omit<ChangeRequest, 'id'>,
): ChangeRequest {
  lastId += 1
  const kept = { ...changeRequest, id: lastId }
  storedChangeRequests[reference] = [...changeRequestsOf(reference), kept]
  return kept
}

/** Whether the event has a change request still waiting for its coordinator. */
export function hasPendingChangeRequest(reference: string): boolean {
  return changeRequestsOf(reference).some((each) => each.status === 'pending')
}

const PENDING_MESSAGE =
  'The organiser has a change request waiting for your decision. Decide the change request first.'

/**
 * SCRUM-57 AC9: the refusal of the event's own decision (approving or rejecting it, rejecting it
 * during planning, confirming it) while it has a Pending change request, or null when it has none.
 */
export function pendingChangeRequestRefusal(reference: string) {
  if (!hasPendingChangeRequest(reference)) {
    return null
  }
  return errorResponse(409, 'change_request_pending', PENDING_MESSAGE)
}

/** Put `changed` in place of the event's request with its id. */
export function replaceChangeRequest(reference: string, changed: ChangeRequest): void {
  storedChangeRequests[reference] = changeRequestsOf(reference).map((changeRequest) =>
    changeRequest.id === changed.id ? changed : changeRequest,
  )
}

/**
 * Close the event's Pending change request as its cancellation does, as
 * `withdraw_pending_change_request_on_cancel`: Withdrawn at the mock's "now", noting why
 * (SCRUM-56 AC9, ADR-0122). A request no longer Pending is left as it is.
 */
export function withdrawPendingChangeRequestOnCancel(reference: string): void {
  for (const changeRequest of changeRequestsOf(reference)) {
    if (changeRequest.status === 'pending') {
      replaceChangeRequest(reference, {
        ...changeRequest,
        status: 'withdrawn',
        withdrawn_at: MOCK_NOW,
        withdrawal_note: CANCELLED_WITHDRAWAL_NOTE,
      })
    }
  }
}

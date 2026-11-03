# ADR-0130: The previous coordinator's notice has its own kind, says the event was reassigned away, and has no link

- **Status:** Accepted. What the notice must say and that it has no link are the Jira ACs as changed on 15 Oct (decisions 1 and 2). The kind's name, the message's words, how the link is left out and keeping the field nullable rather than dropping it are defaults for the reviewer (decisions 3 to 6).
- **Date:** 2026-11-02
- **Story:** SCRUM-28 Receive notifications about my events (AC1's exception); SCRUM-96 Lead reassigns events and oversees coordinator assignments (the previous coordinator's notice); SCRUM-39 Be notified about review and approval decisions (AC6)
- **Supersedes:** [ADR-0041](0041-lead-oversight-and-reassignment.md) decision 4 (the previous coordinator is told with `request_assigned` and a `detail`) and its "Deferred" item
- **Amends:** [ADR-0015](0015-in-app-notifications.md) ("the link is `/events/<reference>`": now except for kinds sent to someone who lost access)

## Context
On a reassignment the coordinator who loses the event is told (SCRUM-96, SCRUM-39 AC6). ADR-0041 decision 4 reused `request_assigned` for them, to avoid a migration, with a `detail` saying the event was no longer theirs. That notice:

- was headed by `request_assigned`'s message, the organiser's: "An Event Coordinator has been assigned to your event request.";
- linked to `/events/<reference>`, an event they can no longer open (SCRUM-87, SCRUM-96 AC5).

The ACs changed on 15 Oct, and an audit of `main` found the notice meets neither:

- **SCRUM-28 AC1:** each notification names the event, says what happened and when, and links to it. The one exception is a notification to someone who has just lost access to the event, such as the previous coordinator after a reassignment: it names the event and says what happened and when, but has no link. Its clarification adds: "A notice that someone lost an event must not be labelled as an assignment, even if the same internal notification type is reused."
- **SCRUM-96:** the previous coordinator's notice names the event, says it has been reassigned away from them and when, never says it has been assigned to them, and has no link. Its clarification leaves the internal type to the developer, as long as everything the coordinator sees says they were removed from the event.
- **SCRUM-39** (changed after completion): the same wording pointer for AC6.

The web app shows a notification's `message`, the event's name as a link, the time and any `detail`. It has no title, label or icon per kind, so the `message` and the link are all that can say "assigned".

## Decision
1. **The previous coordinator's notice says the event was reassigned away from them, never that it was assigned** (SCRUM-28 AC1, SCRUM-96, SCRUM-39 AC6). It names the event (`event_name`, `event_reference`) and says when (`created_at`), like every notification.
2. **It has no link.** The API sends `"link": null` for it. Every other notification keeps `/events/<reference>`, the new coordinator's `coordinator_assigned` and the organiser's `request_assigned` on the same reassignment included.
3. **A new kind, `event_reassigned_away`,** rather than `request_assigned` with a different message or link. The message comes from the kind (ADR-0015), so keeping the kind would mean picking the message and the link from the `detail` text or from who the recipient is, which the notifications module doesn't know. One kind per thing that happened keeps both in one lookup. The name says what happened to the event from the recipient's side and reads after `coordinator_assigned`. `coordinator_unassigned`, the name ADR-0041 floated, was not used: "unassigned" already means an event with no coordinator, in the Lead's queue (SCRUM-95).
4. **Its message is "This event has been reassigned to another Event Coordinator and is no longer yours."** These are the words ADR-0041 put in the old notice's `detail`, so a coordinator reads what they read before, now as the headline. The notice carries no `detail`: the message says it all.
5. **The link is left out by kind.** `NotificationSchema.get_link` returns `None` for the kinds in `NO_LINK_KINDS`, a named set in the notifications schema holding just `event_reassigned_away`. It is not keyed off the `detail` text or the recipient. A later kind for someone who loses access (an organiser's cancelled event, say) joins the set.
6. **`link` stays in every notification, nullable,** rather than being dropped from the no-link ones, so the frontend reads one shape. Its type is `string | null`, and the notifications page shows the event's name as plain text when it is `null`.
7. **Migration 0058 adds the value.** It adds it outside the transaction, as 0054 does. Its downgrade deletes the notices of this kind, then rebuilds `notification_kind` with the 38 kinds 0056 left, in Postgres's order, so other stories' kinds survive it. That is lossy: a downgraded database loses those notices. It revises 0056, main's head when written; open pull requests #166 and #167 also add a migration after 0056 (both numbered 0057), so whichever merges later re-points its `down_revision` (0053 followed 0050 the same way).

## Defaults to review (not agreed with the team)
- **The kind's name, `event_reassigned_away`** (decision 3).
- **The message's words** (decision 4).
- **Leaving the link out by a named set of kinds,** and keeping `link` as a nullable field rather than dropping it (decisions 5 and 6).
- **Leaving notices raised before 0058 as they are** (Consequences). A data migration could turn every `request_assigned` row whose `detail` is the old text into `event_reassigned_away` with no `detail`; it is a follow-up if the team wants old notices to follow the ACs too.

## Consequences
- A reassignment still makes three notification writes, each rolled back and logged on its own if it fails (ADR-0015). The previous coordinator's is logged as `kind=event_reassigned_away`.
- Previous coordinators' notices raised before 0058 keep `request_assigned` and their `detail`, so they still read "An Event Coordinator has been assigned to your event request." and still link. They are not rewritten: a notification is a snapshot (ADR-0015), and nothing in a row says which `request_assigned` went to a previous coordinator other than the `detail` text.
- Any client that reads `link` must handle `null`. The web app is the only one, and its type, page, mock backend and tests change with this record.
- The integration suite can't raise a reassignment: it has one Event Coordinator account, so there is nobody to reassign to. The previous coordinator's notice is checked by the backend's unit tests and the frontend's mock and component tests, and its contract test waits as a todo.

## Revisit when
- Another notification goes to someone who has lost access to the event: add its kind to `NO_LINK_KINDS`.
- The web app gains a title, label or icon per kind: the previous coordinator's must not say "assigned" either (SCRUM-28's clarification).
- The integration run gains a second Event Coordinator account: turn the todo into a real check.

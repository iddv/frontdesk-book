# Assumptions

The idea this product was built from leaves these questions open. Each section says what this version does.

The rules and numbers the idea left open are set as defaults in the product scope, `SCOPE.md` (each marked *(default)*).

## Settings

### Not available yet

These were planned as settings but are **not in this version**: there is no switch to set, and the product behaves one fixed way.

| key | values | proposed default | settles |
|---|---|---|---|
| `practitioner.archive_with_future` | confirm, refused | `refused` | Can a practitioner with future Booked appointments be archived after the admin confirms? |
| `reminders.cancellation_respects_opt_out` | false, true | `true` | Does a patient who opted out of reminders still get a cancellation email? |
| `undo.cancel_after_start` | allowed, refused | `allowed` | May a cancellation be undone once the appointment's start time has passed? |
| `reminders.lead_basis` | elapsed_hours, same_clock_time | `elapsed_hours` | Across a DST change, is '24 hours before' measured in elapsed hours or the same clock time the previous day? |
| `cancel.after_start` | allowed, refused | `allowed` | May a Booked appointment be cancelled after its start time has passed? |
| `reminders.eligibility_checked_at` | booking, send_time | `send_time` | Is reminder eligibility (has email, send reminders on) decided at booking time or at send time? E.g. an email added after booking, or opt-out after booking. |

## Decisions

Questions that aren't a simple switch. For each: the two ways to read it, and what this version does.

### Does 'retried 3 times' mean 4 attempts in total (1 + 3 retries) or 3 attempts in total?

- One reading: Initial attempt plus 3 retries, 4 attempts, Failed after about 30 minutes.
- The other: Same as literal; some readers build 3 total attempts.
- **This version: Initial attempt plus 3 retries, 4 attempts, Failed after about 30 minutes..**

### When a cancellation whose reminder was already Sent is undone, or a reminder was Failed/Skipped before a move, what happens to the reminder?

- One reading: Only moves of Sent reminders trigger a 'changed' email; undo is not covered.
- The other: Undo reschedules a reminder by the normal rules unless one was already sent for this same time.
- **This version: Undo reschedules a reminder by the normal rules unless one was already sent for this same time..**

### How are phone numbers compared for duplicate detection and search (formatting, leading +, country prefixes)?

- One reading: Exact string match.
- The other: Compare digits only, ignoring spaces, dashes and '+'.
- **This version: Compare digits only, ignoring spaces, dashes and '+'..**

### Do the 5 failed sign-ins have to be consecutive, and over what period are they counted?

- One reading: Any 5 failures, ever, since the last lock.
- The other: 5 consecutive failures; a successful sign-in resets the count.
- **This version: it keeps the behaviour it was built with.**

### Can the clinic time zone be changed after first run, and if so, do existing appointments keep their wall-clock time or their absolute instant?

- One reading: The zone is set once at first run and is not editable.
- The other: Not editable in v1; changing it would need a migration design.
- **This version: The zone is set once at first run and is not editable..**

### How are bookings handled at local times that do not exist (spring-forward gap) or occur twice (fall-back) on DST days, and is duration measured in real minutes or wall-clock span?

- One reading: Durations are real minutes; nonexistent start times are refused; repeated times are ambiguous.
- The other: Refuse starts in the gap, take the first occurrence for repeated times, durations in real minutes.
- **This version: it keeps the behaviour it was built with.**

### When an admin changes a practitioner's weekly working hours so existing booked appointments fall outside them, must the system list them and ask for confirmation as with time-off?

- One reading: Not specified: hours save directly and the appointments simply show outside hours.
- The other: Same as time-off: list affected appointments and save after confirmation, flagging them.
- **This version: it keeps the behaviour it was built with.**

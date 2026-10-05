# Scope: FrontDesk Book

FrontDesk Book is an appointment book for a small clinic, installed on the front desk computer and used in a browser by the receptionist. It replaces the paper book: it shows each practitioner's day, lets staff book, move, cancel and close appointments without double-booking, keeps patients' contact details, and emails each patient a reminder automatically before their visit. It holds scheduling and contact data only, never medical notes. The clinic owner installs and runs it; v1 serves one clinic in one time zone.

## Users

- **Admin (clinic owner or practice manager):** sets up the clinic (details, practitioners, working hours, appointment types, email sending, staff accounts) and can do everything a receptionist can. The first admin account is created on first run (F1). Signs in with username and password.
- **Receptionist:** books, moves, cancels and closes appointments, manages patients, watches reminder status, prints the day sheet and exports appointments. Signs in with a staff account the admin creates. Cannot change clinic setup, settings or staff accounts.
- **Patients:** do not sign in. They are records with contact details and they receive reminder emails.
- **Practitioners:** are records, not users, in v1. Their schedules are run by the front desk.

## Core flows

### F1: Install and first run
- Who: Admin
- Steps:
  1. The operator follows the README on a fresh machine and runs the single install-and-start command.
  2. The service starts on 127.0.0.1 and prints the address to open.
  3. The browser shows a first-run screen because no accounts exist. The operator enters the clinic name, the clinic time zone (pre-filled from the machine), an admin username and a password typed twice.
  4. The system checks the password rules, creates the admin, records the clinic, and signs them in.
  5. The admin sees an empty day view with a checklist: add practitioners, set hours, add appointment types, configure email.
  6. Running the documented demo command (for example `--demo`) on an empty install loads the demo data described in Install and run.
- When it goes wrong:
  - Passwords differ or are too short: the form shows the rule and keeps the other fields.
  - Port in use: startup exits with a message naming the port and the setting that changes it.
  - First-run screen requested after an admin exists: it redirects to sign-in.
  - Demo command on a non-empty database: it refuses and changes nothing.

### F2: Set up the clinic and staff
- Who: Admin
- Steps:
  1. The admin edits the clinic details: name, address, phone and reply-to email. These details appear in reminders.
  2. The admin adds practitioners (display name, optional title, calendar colour), sets each one's weekly working hours (one or more time ranges per weekday), and adds time-off blocks (date or date range, optionally part of a day, with a short label such as "Leave").
  3. The admin adds appointment types: a name and a default duration. Types can be archived; they cannot be deleted once used.
  4. The admin configures email (see Install and run) and clicks "Send test email" to a chosen address. The result is shown.
  5. The admin creates receptionist and admin accounts, resets a staff password (giving a one-time password that must be changed at next sign-in), and deactivates accounts.
  6. The admin changes the operator settings.
- When it goes wrong:
  - Overlapping hour ranges on one day, or end time before start time: the range is rejected with the reason.
  - A time-off block or archived practitioner overlaps existing booked appointments: the system lists those appointments and saves only after the admin confirms. The appointments stay booked and are flagged "outside hours" on the day view.
  - The test email fails: the server's error text is shown and the settings are kept.
  - The admin tries to deactivate themselves while they are the last active admin: refused.
  - A receptionist opens any setup page: "Not allowed" is shown.

### F3: Manage patients
- Who: Receptionist, Admin
- Steps:
  1. The user searches by part of a name, a phone number, an email or a date of birth. Results show name, date of birth, phone and next appointment.
  2. The user adds a patient: first and last name (required), date of birth, mobile phone, email, and "send reminders" (on by default). At least one of phone or email is required.
  3. The system validates the fields and checks for likely duplicates (same name and date of birth, or same phone or email). Any match is shown with "Use existing" or "Create anyway".
  4. The user opens a patient to see their details and their past and future appointments, edits details, or archives the patient.
  5. Archived patients are hidden from search unless "include archived" is ticked, and they can be restored.
- When it goes wrong:
  - Invalid email or phone format: an error is shown on the field.
  - Archiving a patient who has future booked appointments: refused until those are cancelled or moved, and the appointments are listed.
  - Patient not found (for example archived by another user mid-edit): a message is shown and the user returns to search.

### F4: Book an appointment
- Who: Receptionist, Admin
- Steps:
  1. From the day view, the user clicks a free slot in a practitioner's column, or uses "New appointment" and picks a practitioner, date and time.
  2. The user picks or creates the patient (F3), picks the appointment type (which fills the duration, editable in 5-minute steps), and optionally adds a booking note.
  3. The system checks the slot against the rules in Domain rules (overlap, working hours, time-off, past time).
  4. The system saves the appointment as Booked, records who booked it and when, and schedules its reminder.
  5. The appointment appears on the day view and on the patient's record. A confirmation shows the reminder status ("Reminder due Mon 9 Mar 10:00", or "No reminder: no email").
- When it goes wrong:
  - The practitioner already has an appointment in that time: "Conflicts with <patient> 10:00–10:30" is shown and nothing is saved.
  - Another user took the slot a moment earlier: the same conflict message is shown and the day view refreshes.
  - Outside working hours or in time-off: blocked, or a warning with confirm, depending on `booking.outside_hours`.
  - The patient has another appointment at that time: blocked, or a warning, depending on `booking.patient_overlap`.
  - Start time is in the past: refused.
  - Practitioner or type is archived: it is not offered in the pickers.

### F5: View the day and move appointments
- Who: Receptionist, Admin
- Steps:
  1. The day view shows one column per active practitioner. Working hours are shaded, time-off is blocked out, and each appointment shows time, patient name, type, status and reminder state. The user can go to today, the previous or next day, or a picked date, and can filter to chosen practitioners.
  2. A week view for one practitioner shows the same information for 7 days.
  3. The user opens an appointment to see details and its history (who created, changed, moved or cancelled it, and when).
  4. To move it, the user chooses "Move" and picks a new date, time and/or practitioner, or changes the duration. The same checks as F4 run.
  5. The system saves the move, records the old and new times in the history, and reschedules the reminder (see Domain rules). The user sees the appointment in its new place.
- When it goes wrong:
  - Conflict at the new time: the conflict message is shown and the appointment stays where it was.
  - Someone else changed the appointment since it was opened: "This appointment was changed by <user>; reload" is shown and nothing is saved.
  - The appointment is cancelled, attended or no-show: "Move" is not offered.

### F6: Cancel, close and undo
- Who: Receptionist, Admin
- Steps:
  1. The user opens a booked appointment and chooses "Cancel", picking a reason: patient cancelled, clinic cancelled, or other (with a short text).
  2. The system marks it Cancelled. It keeps the record, frees the slot, stops any pending reminder, flags the cancellation as late if it falls inside the late window, and sends a cancellation email if `reminders.cancellation_email` is on.
  3. After the start time, the user marks a booked appointment Attended or No-show. The day view offers both directly on each appointment.
  4. "Undo" on a cancelled, attended or no-show appointment returns it to Booked. For a cancelled one, the F4 conflict checks run again. The history records every change.
- When it goes wrong:
  - Marking attended or no-show before the start time: refused.
  - Undoing a cancellation when the slot has since been taken: the conflict is shown and the appointment stays Cancelled; the user can move it instead.
  - Undoing anything older than the undo limit: refused (see Domain rules).

### F7: Automatic reminder emails
- Who: System; Receptionist and Admin monitor
- Steps:
  1. A background job in the service runs every minute and sends due reminders by the rules in Domain rules. The email contains the patient's first name, date, time, practitioner, clinic name, address and phone, and "to change or cancel, call <clinic phone>". It never includes the type, the booking note or any clinical text.
  2. Each send attempt is logged with time, recipient and result. The appointment shows its reminder state: Pending, Sent, Failed, Skipped (no email, opted out, or too late), or Not needed (cancelled).
  3. A "Reminders" page lists the next 2 days' reminders and all failures from the last 7 days. The user can retry a failed reminder, or send now with "Resend".
  4. A banner on every page shows when email is not configured, or when the last 3 sends failed.
- When it goes wrong:
  - The mail server is unreachable: the send is retried 3 times, 10 minutes apart (default), then marked Failed and shown on the page.
  - The patient has no email or has opted out: marked Skipped with the reason, and the receptionist can phone them instead.
  - The computer was off at send time: on start the job sends any reminder still due if the appointment is more than 1 hour away; otherwise it marks it Skipped (too late).

### F8: Day sheet, export and backup
- Who: Receptionist, Admin (backup and restore: Admin)
- Steps:
  1. The user opens "Day sheet" for a date and practitioner(s). It is a printable page per practitioner listing time, patient name, phone, type and status, with totals per status.
  2. The user exports appointments for a date range (maximum 366 days) as CSV, with one row per appointment: date, start, end, practitioner, patient, phone, email, type, status, cancel reason, late flag, reminder state, created by.
  3. The user opens the "Summary" for a date range to see, per practitioner, the counts of booked, attended, no-show, cancelled and late-cancelled appointments, plus reminders sent and failed.
  4. The admin clicks "Download backup" to get a single file of all data, and can restore one using the documented command (Install and run).
- When it goes wrong:
  - End date before start date, or range over 366 days: an error is shown.
  - A range with no appointments: the CSV has only the header, and the screen says "No appointments".
  - A receptionist tries to back up: "Not allowed" is shown.

## Features

### Must have (v1)
- M1: Single-command install, first-run admin creation, opt-in demo data (F1)
- M2: Staff accounts with admin and receptionist roles, sign-in, password reset, deactivation (F1, F2)
- M3: Clinic details, practitioners, weekly working hours, time-off blocks, appointment types (F2, F4, F5)
- M4: Patient records with search, duplicate warning, edit, archive and restore (F3, F4)
- M5: Booking with atomic overlap, hours and past-time checks (F4)
- M6: Day view across practitioners and week view per practitioner, with date navigation and filter (F4, F5, F6)
- M7: Move, cancel with reason, attended/no-show, undo, and a full per-appointment history (F5, F6)
- M8: Background reminder sender with retry, catch-up after downtime, reschedule and cancellation emails, SMTP or log mode, test email (F2, F6, F7)
- M9: Reminders page with send log, failures, retry and resend, and a status banner (F7)
- M10: Printable day sheet, date-range summary and CSV export (F8)
- M11: Backup download, restore command, versioned schema migrations (F1, F8)
- M12: Operator settings page (F2)

### Later (not in v1)
- SMS reminders: needs a paid provider; email covers the idea.
- Patient self-booking or confirm/cancel links in emails: needs public hosting and patient identity.
- Practitioner logins and personal calendars: the front desk runs the book in v1.
- Recurring appointments and waiting lists: can be booked one by one for now.
- Calendar sync (Google, Outlook, iCal feeds): an integration, not core.
- Billing, invoicing or payments: the idea limits the product to scheduling.
- Multiple clinics or locations, multi-tenant hosting: v1 serves one clinic.
- Clinical notes or attachments: excluded by the idea.

## Domain rules and defaults

- **Time:** all times use the clinic time zone set at first run; times are stored with that zone and handle DST changes correctly. The time grid uses 5-minute steps (default). Durations run from 5 to 480 minutes.
- **Default hours** for a new practitioner: Mon–Fri 09:00–17:00 (default). The day view shows 07:00–20:00 (default).
- **Overlap:** two non-cancelled appointments for the same practitioner may not overlap. An appointment ending at 10:00 and one starting at 10:00 do not overlap. Cancelled appointments never block.
- **Patient overlap:** governed by `booking.patient_overlap`.
- **Past:** a new booking or move may not start before the current time rounded down to the 5-minute grid. Today's earlier slots are closed.
- **Statuses:** Booked, Attended, No-show, Cancelled. Only Booked can be moved. Attended and No-show can be set only from the start time onward.
- **Late cancellation:** a cancellation made less than 24 hours before the start (default).
- **Undo** of a status change is allowed until the end of the day after the appointment's date (default).
- **Reminder timing:** one reminder per appointment, sent 24 hours before the start (default).
  - If booked or moved inside that window, it is sent immediately, provided the start is more than 2 hours away (default); otherwise it is Skipped (too late).
  - When an appointment with a Sent reminder is moved, a new reminder is sent for the new time by the same rules, with the subject "Your appointment has changed".
  - Only patients with an email and with "send reminders" on get emails.
- **Booking note:** maximum 200 characters, labelled "Scheduling note, no clinical information". It is never emailed.
- **Patient fields:** names up to 100 characters; phone 6–20 digits, optional leading +, with spaces and dashes allowed; email must be a valid address; date of birth may not be in the future.
- **Passwords:** at least 10 characters. 5 failed sign-ins lock the account for 15 minutes (default). A session ends after 8 hours of inactivity (default).
- **Archiving:** practitioners and types used by any appointment are archived, never deleted. A practitioner with future booked appointments cannot be archived until those are moved or cancelled.

## Operator settings

| key | values | default | what it decides |
|---|---|---|---|
| `booking.outside_hours` | block, warn | warn | Whether booking outside working hours or in time-off is refused or allowed after confirmation. |
| `booking.patient_overlap` | block, warn | warn | Whether a patient may hold two overlapping appointments with different practitioners. |
| `reminders.cancellation_email` | on, off | on | Whether a patient with email gets a short email when their appointment is cancelled. |
| `patients.reminder_default` | on, off | on | Whether "send reminders" starts ticked for new patients. |

## Money and data integrity

The product handles no money. For integrity:

- Appointments are never deleted. Cancellation, moves and status changes are recorded as history entries showing user, time, and old and new values. Patients, practitioners and types are archived, never deleted.
- The overlap check and the save happen in one atomic step, so two receptionists booking the same slot at the same moment yield exactly one booking. The other user sees the conflict.
- Every editable record carries a version. A save made against a stale version is rejected with a "changed by someone else" message.
- Each reminder is sent at most once per appointment time. Its send is recorded before the job moves on, so a restart never sends a duplicate. "Resend" is the only way to send again, and it is logged.
- All input is validated on the server before saving, with field-level messages. Summary counts always equal the number of matching appointment records.

## Install and run

- One documented command installs dependencies, creates the data store, applies migrations and starts the service. A second documented command (or a flag) runs it as a background service that starts with the computer.
- **Safe defaults:**
  - It listens on 127.0.0.1:8080 (default) unless configured, and the README explains how to allow other front desk PCs on the LAN.
  - A fresh install starts empty.
  - The first admin is created on the first-run screen with a password the operator chooses. There is no default password or built-in secret; the session secret is generated randomly at first start and stored in the data directory.
- **Demo data** is loaded only by the explicit demo command on an empty database. It contains:
  - 3 practitioners with differing hours and one time-off block, and 4 appointment types;
  - 60 patients, some without email and some opted out, all on `example.com` addresses;
  - about 150 appointments across the past 2 weeks and the next 2 weeks, in every status;
  - a demo admin and a demo receptionist whose random passwords are printed once.
- **Email mode:**
  - `smtp` sends through the configured server (host, port, TLS mode, username, password, from address).
  - `log` (the default until SMTP is configured, and always the mode in demo) writes each email to an outbox file in the data directory instead of sending.
- **Configuration:** environment variables or a config file, all documented in the README: listen address and port, data directory, email mode and SMTP options, and log level.
- **Data and upgrades:**
  - All data lives in the data directory.
  - Backup is the in-app download (F8) or a backup command. Restore is a command that takes a backup file, refuses while the service is running, and keeps the replaced data as a timestamped copy.
  - The schema is versioned. Upgrades apply migrations automatically at start after taking an automatic backup.

## Non-functional basics

- **Roles:** the permissions in Users are enforced on the server for every action, not only hidden in the interface.
- **Errors:** validation messages are clear and name the field. Errors never show a stack trace to users.
- **Persistence:** all data and pending reminders survive restarts and power loss.
- **Audit:** appointment history (F5), staff account changes, settings changes and the reminder send log are kept for the life of the data.
- **Logging:** passwords and SMTP credentials never appear in logs or exports.
- **Interface:** works in current desktop browsers, and the day sheet prints cleanly on A4 and Letter.
- **Tests:** automated tests cover overlap and concurrency, DST-day booking, reminder timing (including the catch-up, move and too-late cases), permissions, undo and export. One documented command runs them.

## Definition of done

- [ ] F1: Install and first run — on a fresh machine the README command starts the service on 127.0.0.1; the first-run screen creates the admin, who lands on an empty day view; the demo command fills the system and refuses on non-empty data.
- [ ] F2: Set up the clinic and staff — practitioners show with their hours and time-off on the day view, types appear in booking, the test email arrives (or appears in the outbox in log mode), and a new receptionist can sign in but cannot open setup.
- [ ] F3: Manage patients — a patient can be added, found by phone fragment, edited and archived; a duplicate warning appears for a same-name-and-DOB entry; archiving with future appointments is refused.
- [ ] F4: Book an appointment — a booking appears on the day view with its reminder due time; booking an overlapping slot, including from two browsers at once, yields exactly one appointment and one conflict message.
- [ ] F5: View the day and move appointments — the day and week views navigate by date; a moved appointment shows at its new time with old and new times in its history; a stale edit is rejected.
- [ ] F6: Cancel, close and undo — a cancellation frees the slot, records the reason and late flag, and stops the reminder; attended and no-show work only after the start time; undo restores Booked or reports a conflict.
- [ ] F7: Automatic reminder emails — a reminder is sent 24 hours before the visit, logged once and shown as Sent; with SMTP down it retries and then shows Failed with a working Retry; after downtime, due reminders are caught up or Skipped (too late).
- [ ] F8: Day sheet, export and backup — the day sheet prints per practitioner with status totals; the CSV for a range matches the summary counts; a downloaded backup restored with the command reproduces all appointments and patients.

# FrontDesk Book

An appointment book for a small clinic. It runs on the front desk computer and the receptionist uses it in a browser.
Staff can see each practitioner's day, book, move, cancel and close appointments without double-booking, and keep
patient contact details. Reminder emails go out to patients automatically. It holds scheduling and contact data only,
never medical notes.

## At a glance

- **What it is:** A self-hosted appointment book for small clinics that lets the receptionist schedule patients by provider and time slot and email them reminders before their visit.
- **Who it's for:** Receptionists at small independent clinics (a few practitioners, e.g. physio, dental, GP or therapy practices) who still keep the appointment book on paper.
- **Quick start:**

  ```sh
  git clone https://github.com/iddv/frontdesk-book.git
  cd frontdesk-book
  python3 frontdesk.py
  ```

The rest of this README covers configuration, data, backup and the full guide; SECURITY.md and READINESS.md say what was checked before this release.

## Requirements

- **Python 3.9 or newer.** Nothing else: FrontDesk Book uses only the Python standard library, so there are no packages to install.
  - Windows: install Python from python.org and tick "Add Python to PATH".
  - macOS and Linux: Python 3 is usually already installed.
- The clinic time zone must be known to the system time zone database.
  - Linux and macOS have it built in.
  - On Windows, run `py -m pip install tzdata` once.

## Install and start (one command)

```sh
python3 frontdesk.py
```

This command:

1. creates the data directory (`./data` by default);
2. creates the database and applies migrations;
3. generates a random session secret in `data/secret.key`;
4. starts the reminder job;
5. listens on **127.0.0.1:8080** and prints the address to open.

Open http://127.0.0.1:8080/. On a fresh install you see the first-run screen. Enter the clinic name, the time zone
(pre-filled from this computer), an admin username and a password (at least 10 characters, typed twice). You are
signed in and see an empty day view with a "Getting started" checklist. There is no default password.

Stop the service with Ctrl+C.

### Start automatically with the computer

```sh
python3 frontdesk.py install-service
```

- **Linux:** writes and enables a systemd user unit, `frontdesk-book.service`, and enables lingering so it starts at boot.
- **macOS:** installs a LaunchAgent.
- **Windows:** creates a scheduled task that runs at logon.

The service uses the data directory and config file that were in effect when you ran the command.

### Demo data

```sh
python3 frontdesk.py demo          # load demo data and exit
python3 frontdesk.py --demo        # load demo data, then start the service
```

The demo command works only on an empty install, meaning no accounts and no patients. Otherwise it refuses and
changes nothing. It loads:

- 3 practitioners with different hours, one with a time-off day;
- 4 appointment types;
- 60 patients on `example.com` addresses, some without email and some opted out of reminders;
- about 150 appointments across the past and next 2 weeks, in every status;
- the accounts `demo-admin` and `demo-reception`. Their random passwords are printed once.

Demo installs always use email **log** mode.

## Configuration

Set options in a `frontdesk.conf` file in the working directory, or point `FRONTDESK_CONFIG` at one. Environment
variables override the file. See `frontdesk.conf.example`.

| setting (file / environment)                     | default     | meaning                                     |
|--------------------------------------------------|-------------|---------------------------------------------|
| `host` / `FRONTDESK_HOST`                        | `127.0.0.1` | address to listen on                        |
| `port` / `FRONTDESK_PORT`                        | `8080`      | port to listen on                           |
| `data_dir` / `FRONTDESK_DATA_DIR`                | `./data`    | where all data lives                        |
| `log_level` / `FRONTDESK_LOG_LEVEL`              | `INFO`      | `DEBUG`, `INFO`, `WARNING`, `ERROR`         |
| `email_mode` / `FRONTDESK_EMAIL_MODE`            | (page)      | `smtp` or `log`                             |
| `smtp_host` / `FRONTDESK_SMTP_HOST`              | (page)      | mail server                                 |
| `smtp_port` / `FRONTDESK_SMTP_PORT`              | (page)      | e.g. 587                                    |
| `smtp_tls` / `FRONTDESK_SMTP_TLS`                | (page)      | `starttls`, `ssl` or `none`                 |
| `smtp_user` / `FRONTDESK_SMTP_USER`              | (page)      | SMTP username                               |
| `smtp_password` / `FRONTDESK_SMTP_PASSWORD`      | (page)      | SMTP password                               |
| `smtp_from` / `FRONTDESK_SMTP_FROM`              | (page)      | from address                                |

If port 8080 is taken, startup stops with a message naming the port. Set `FRONTDESK_PORT`, or `port=` in the config
file, to use another port.

### Email

Admins set up email under **Setup → Email sending** and can send a test email from that page. Any email setting in the
config file or environment overrides the page, and the page says which settings are fixed that way.

- **log** (the default until SMTP is configured): each email is appended to `data/outbox.log` instead of being sent.
  A banner on every page says that email is not configured.
- **smtp**: emails are sent through your mail server, for example your email provider's SMTP service with an app password.

### Using it from other front desk PCs on the LAN

By default only this computer can open FrontDesk Book. To allow other PCs:

1. Set `host = 0.0.0.0` in `frontdesk.conf`, or `FRONTDESK_HOST=0.0.0.0`.
2. Restart the service.
3. Allow the port through this computer's firewall, for the local network only.
4. On the other PCs, open `http://<this-computer's-LAN-IP>:8080/`.

Traffic is plain HTTP, so only do this on a trusted clinic network. Never forward the port to the internet.

### Health check

`GET /health` needs no sign-in. It answers `200 ok` when the database can be opened, and `503` when it can't.
Use it from a monitoring tool or a script, for example `curl -f http://127.0.0.1:8080/health`.

## Backup, restore and upgrades

- **Backup in the app:** an admin opens **Setup → Backup → Download backup**. This gives a single file containing all data.
- **Backup from the command line:** `python3 frontdesk.py backup [file]`. Without a file name it writes to `data/backups/`.
- **Restore:** stop the service, then run `python3 frontdesk.py restore <backup-file>`.
  - Restore refuses while the service is running.
  - The data being replaced is kept as `data/replaced-<timestamp>.db`.
- **Upgrades:** replace the program files and start as usual. If the schema version changed, a backup is written to
  `data/backups/pre-upgrade-*.db` and the migrations are applied automatically.

Backups contain patient contact details and the SMTP password, if one is set. Store them as carefully as the computer itself.

## Running the tests

```sh
python3 frontdesk.py test
```

The tests cover:

- overlap rules, and 8 concurrent bookings of the same slot;
- booking on DST days, including spring-forward and fall-back;
- reminder timing: normal, inside the window, too late, catch-up after downtime, moves, retries and failure,
  interrupted sends, cancellation and resend;
- status changes and undo, including the undo limit and undo conflicts;
- patient validation, duplicate warnings and search;
- CSV export against the summary counts, and backup/restore;
- server-side permissions through real HTTP requests, CSRF, lockout and the last-admin rule.

There are no third-party dependencies to install or pin: everything comes from the Python standard library. The same
command runs on every push and pull request (`.github/workflows/test.yml`).

## Troubleshooting

- **"Port 8080 … is already in use" at start:** another program (or a second copy of FrontDesk Book) has the port. Stop it, or
  set `FRONTDESK_PORT` / `port=` to another port.
- **Other PCs can't open the page:** the service listens on 127.0.0.1 by default. Follow "Using it from other front desk
  PCs on the LAN" and check the firewall.
- **Unknown time zone on Windows:** run `py -m pip install tzdata` once, then start again.
- **A staff member is locked out:** after 5 wrong passwords an account is locked for 15 minutes. Wait, or have an admin
  reset the password under **Setup → Staff accounts**.
- **The only admin forgot their password:** restore a backup taken when the password was known, or start a fresh data
  directory. There is no built-in recovery password.
- **Signed out unexpectedly:** a session ends after 8 hours without activity, when the password is changed in another
  browser, or when the account is deactivated or its password reset.
- **Reminders are not arriving:** check the banner and the **Reminders** page. In `log` mode emails go to
  `data/outbox.log` and are not sent. Use **Send test email** on the email setup page; the mail server's error is shown.
  Failed reminders can be retried from the Reminders page.
- **Is it running?** `curl -f http://127.0.0.1:8080/health` answers `ok`, or 503 if the database can't be opened
  (check that the data directory exists and the service's user can read and write it).
- **Restore refuses to run:** the service is still running. Stop it (Ctrl+C, or stop the background service) and retry.
- **Something went wrong page:** the details are in the service's log output (the terminal, or the system service log).
  Raise the detail with `FRONTDESK_LOG_LEVEL=DEBUG`.

## Known limitations

- One clinic, one time zone. No multiple locations.
- Email reminders only. No SMS, and no confirm or cancel links for patients.
- Patients don't sign in and can't book themselves. Practitioners are records, not users.
- No recurring appointments, waiting lists or calendar sync.
- No billing, and no clinical notes or attachments.
- Plain HTTP. Use it on this computer or a trusted clinic network only; never expose it to the internet.
- The reminder job runs inside the service, so reminders are only sent while it is running. Missed reminders are caught
  up at the next start if the appointment is still more than 1 hour away.
- Designed for a handful of front desk users at once, with all data in one SQLite file on this computer.

## Rules worth knowing

- **Time:** all times are in the clinic time zone chosen at first run and are stored in UTC, so DST changes are handled.
  A time that doesn't exist on a spring-forward day is refused.
- **Overlap and saving:** the overlap check and the save happen in one database transaction. Two people booking the
  same slot at once get exactly one booking; the other person sees "Conflicts with …".
- **Concurrent edits:** every editable record has a version. A save based on a stale version shows "changed by <user>; reload".
- **Reminders:**
  - One reminder per appointment time, 24 h before the start.
  - Booked or moved inside that window: sent at once if the start is more than 2 h away, otherwise skipped (too late).
  - The job runs every minute and once at start-up. A reminder that is due is still sent if the appointment is more
    than 1 h away; otherwise it is skipped (too late).
  - A failed send is retried 3 times, 10 minutes apart, then marked Failed.
  - Each attempt is recorded before the email is sent, so a crash can't cause a silent duplicate. A send that was
    interrupted is marked Failed and can be resent by hand.
  - **Resend** is the only way to send a reminder again.
- **Undo:** allowed until the end of the day after the appointment's date.
- **Practitioners:** a practitioner with future booked appointments can't be archived until those are moved or
  cancelled. Adding time-off over booked appointments lists them and asks for confirmation; they stay booked and are
  flagged "outside hours".
- **Logging:** request logs hold only the method and path, never form bodies or query strings. Passwords and SMTP
  credentials are never logged or exported to CSV.

## Layout

```
frontdesk.py            launcher / CLI
frontdesk/config.py     configuration loading
frontdesk/db.py         SQLite schema, migrations, backup/restore
frontdesk/domain.py     business rules (booking, reminders, patients, reports)
frontdesk/mailer.py     SMTP and log-mode email
frontdesk/web.py        HTTP server, sessions, permissions, pages
frontdesk/demo.py       demo data
tests/                  automated tests
```

## Acceptance tests

End-to-end checks of the product's behaviour are in `tests/acceptance/` (they need pytest):

    python -m pytest tests/acceptance

4 of them are known open items, marked as expected failures and listed in `tests/acceptance/README.md`; the suite stays green.

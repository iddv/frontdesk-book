# AGENTS.md — FrontDesk Book

A self-hosted appointment book for small clinics that lets the receptionist schedule patients by provider and time slot and email them reminders before their visit.

Built by an autonomous build (see NOTICE); maintained through GitHub issues by the owner, by
bears, and by any coding agent that reads this file. CLAUDE.md imports this file.

## What this is

- **For:** Receptionists at small independent clinics (a few practitioners, e.g. physio, dental, GP or therapy practices) who still keep the appointment book on paper.
- **Does:** FrontDesk Book is an appointment book for a small clinic, installed on the front desk computer and used in a browser by the receptionist.
- **Stack:** Python 3.9+, standard library only, SQLite, one process on 127.0.0.1.
- **Scope:** `SCOPE.md` (users, numbered flows F1–F8, domain rules, definition of done).
  `ASSUMPTIONS.md` lists the questions the idea left open and what this version does.

## Setup, run, test

These commands are run by CI exactly as written (`.github/workflows/ci.yml`, job `agents-md`).
If you change a command, change it here in the same commit. A line marked `# serve` starts the
service; the check waits for it to answer on 127.0.0.1, then stops it.

```sh
python3 frontdesk.py   # serve: http://127.0.0.1:8080/ (port: FRONTDESK_PORT)
python3 frontdesk.py test   # the product's own tests
python -m pip install pytest==8.3.3 && python -m pytest tests/acceptance   # the acceptance suite
```

- pytest is only needed for the acceptance suite; install it inside a virtual environment if
  your system Python refuses.
- Demo data: `python3 frontdesk.py demo` (empty install only).
- Backup and restore: `python3 frontdesk.py backup [file]`, `python3 frontdesk.py restore <backup-file>`.
- Configuration: environment variables or `frontdesk.conf` (see README › Configuration).

## Architecture in brief

| Path | Holds |
|---|---|
| `frontdesk/app.py` | Command line: run (default), demo, backup, restore, install-service, test. |
| `frontdesk/config.py` | Configuration: defaults < config file < environment variables. |
| `frontdesk/db.py` | SQLite storage, versioned migrations, backup and restore. |
| `frontdesk/demo.py` | Demo data, loaded only on an empty install. |
| `frontdesk/domain.py` | Business rules: time handling, validation, patients, booking, statuses, reminders, reports. |
| `frontdesk/mailer.py` | Email sending: SMTP, or 'log' mode that appends to an outbox file in the data directory. |
| `frontdesk/web.py` | HTTP layer: routing, sessions, permissions and server-rendered pages. |
| `frontdesk.py` | The launcher the README uses: `python3 frontdesk.py` starts the service; `python3 frontdesk.py test`, `python3 frontdesk.py demo`, `python3 frontdesk.py backup`, `python3 frontdesk.py restore <backup-file>` are its other commands. |
| `tests/test_frontdesk.py` | Automated tests: overlap & concurrency, DST, reminder timing, permissions, undo, export, backup. |
| `tests/acceptance/` | The acceptance suite: one file per behaviour, through the real interface (pytest). |
| `tests/acceptance/_helpers/` | Drivers the acceptance tests share (start the service, sign in, submit forms). |

Data lives in `./data`; the schema is versioned (the schema version is stored with the data; pending migrations run at start), and a
pre-migration backup is written before any upgrade.

Practitioners and types used by any appointment are archived, never deleted. Appointments are never deleted.

## Conventions

- Standard library only. Do not add a dependency to fix a bug.
- Operator settings (binary business rules) are settings with an environment override; a new one
  goes in the Settings page, the README table, `ASSUMPTIONS.md`, and gets an acceptance test per
  value. Never hard-code one side of a business rule.
- Every behaviour has one acceptance test file, `tests/acceptance/test_<what_it_checks>.py`,
  with a plain docstring (what it checks, what is expected, where the rule comes from). Helpers
  live in `tests/acceptance/_helpers/` and drive the product's real interface.
- The server checks roles and CSRF on every state-changing request; templates escape everything.
- Plain words in user-facing files: no build-process jargon, no internal ids.

## The acceptance suite, readiness and security

- `tests/acceptance/README.md` lists the **known open items**: tests marked
  `xfail(strict=False)` because the behaviour is not there yet. **To fix one:** make the test
  pass, then delete the mark block at the end of its file and the line in that README. CI fails
  if an xfail test now passes and still carries the mark.
- `READINESS.md` is the operational scorecard (install, localhost default, empty start, first
  admin, backup, restart, logs, CI, docs). Keep it true: a change that moves an item from amber
  to green edits the row.
- `SECURITY.md` is the threat model, what was probed, and the findings with their status. A fix
  for a finding changes its status there and names its test. Report new weaknesses privately
  (see its last section), never in a public issue.

## Operator settings

Planned as settings but **not in this version** (the product behaves one fixed way; see `ASSUMPTIONS.md`): `practitioner.archive_with_future`, `reminders.cancellation_respects_opt_out`, `undo.cancel_after_start`, `reminders.lead_basis`, `cancel.after_start`, `reminders.eligibility_checked_at`.

## Maintenance protocol (issues and labels)

Labels are the state; GitHub is the only record. `.github/labels.yml` defines them.

1. **Pick** an open issue labelled `go` with no assignee and no `claim:*` label (or one whose
   lease comment has expired and that has no open linked PR). `p1` before `p2` before `p3`.
2. **Claim** it: a person assigns themself; an agent adds `claim:agent` and a comment
   `<!-- bears:claim lease_until=<UTC+6h> branch=<branch> -->  Working on this.` Leave issues
   with `claim:bears` or an assignee alone.
3. **Branch** from `main`: `<who>/<N>-<slug>` (bears uses `bears/<N>-<slug>`).
4. **Reproduce first:** write `tests/acceptance/test_<slug>.py` that fails on `main` for the
   reason the issue describes. If you cannot make it fail, label `cannot-reproduce`, say why in a
   comment, remove your claim, and stop.
5. **Fix** with the smallest change that makes it pass without weakening another test.
6. **Verify:** run every command in *Setup, run, test*; the whole suite must be green; the
   README's quick start must still work as written.
7. **Documents:** update this file if a command, module or convention changed; `READINESS.md`
   or `SECURITY.md` if a row changed; add a line under *Unreleased* in `CHANGELOG.md`.
8. **Open a PR** with the template (`.github/pull_request_template.md`): what and why, the
   failing test's name, the verification you ran, and `Fixes #N`. Remove your claim label; the
   PR is now the lock. **Never push to `main`. Never change `.github/workflows/` in a fix PR.**
   Never commit a secret, a database file or demo credentials.
9. The owner reviews and merges on GitHub. A release follows (`.github/bears.yml` ›
   `release.on_merge`).

bears follows exactly these steps; its comments carry `<!-- bears:… -->` markers and the PR
label `bears`. Policy for this repo: `.github/bears.yml`.

## Provenance

Generated by an autonomous software build from a short product brief, with automated checks (its tests, a walk of every documented flow, a security review and a readiness review) before release. See `NOTICE`, `LICENSE` and `READINESS.md`.

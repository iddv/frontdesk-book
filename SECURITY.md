# Security

How FrontDesk Book was reviewed for security before its first release, what was found, and what is still open.

## Threat model

A clinic appointment book served over HTTP on 127.0.0.1:8080 (optionally the LAN). Everything except first-run setup and sign-in requires a staff session; setup pages require the admin role. It holds patient contact data, staff password hashes and the SMTP password in a SQLite file in the data directory. Uses only the Python standard library.

### Entry points

| entry point | who can reach it | authentication | notes |
|---|---|---|---|
| GET/POST /setup | public | none; only works while no account exists, afterwards redirects to /login | creates the first admin |
| GET/POST /login | public | username + password; 5 failures lock the account for 15 minutes | CSRF token tied to a pre-session cookie |
| POST /logout, GET/POST /password | staff | session cookie + CSRF token |  |
| day/week views, /appt/*, /patients/*, /reminders, day sheet, summary, export CSV | staff | session cookie (fd_session, HttpOnly, SameSite=Strict); POSTs need a CSRF token | receptionist and admin |
| /admin/* (clinic, practitioners, hours, time-off, types, email + test email, staff accounts, settings, backup download) | admin | session cookie + admin role checked on the server + CSRF token |  |
| HTTP request parsing (Handler._go) | public | none; runs before any authentication | reads Content-Length and the body before routing |
| CLI: frontdesk.py [demo\|--demo\|backup\|restore\|install-service] | local | the machine's user | restore refuses while the service holds data/service.lock |
| Background reminder job (every minute) | local | n/a | sends via SMTP or writes data/outbox.log |
| Config: frontdesk.conf and FRONTDESK_* environment variables | local | file system | may contain the SMTP password |

### Assets

| asset | kind | where |
|---|---|---|
| patient names, dates of birth, phones, emails, appointments | personal data | data/frontdesk.db, CSV exports, backups, data/outbox.log |
| staff password hashes (PBKDF2-SHA256, 240k rounds, salted) | secrets | data/frontdesk.db |
| SMTP password | secrets | data/frontdesk.db or frontdesk.conf |
| session/CSRF signing secret | secrets | data/secret.key (mode 600) |
| integrity of the appointment book and its history | integrity | data/frontdesk.db |
| availability of the front desk service | availability | the running process |

## What was checked, and how

The product was started as its README says and probed while running.

| area | check | result | evidence |
|---|---|---|---|
| authN/authZ | anonymous GET of /day, /patients, /admin, /admin/backup/download, /export, /reminders | pass | all 303 to /login |
| authN/authZ | receptionist GET of /admin, /admin/staff, /admin/settings, /admin/email, /admin/backup/download | pass | 403 'Not allowed' on each |
| authN/authZ | receptionist POST (valid CSRF token) to create an admin, change a role, change settings | pass | 403 on each; checked by an automated test |
| authN/authZ | first-run /setup after an admin exists | pass | GET 303 to /login; POST refused with 400 |
| authN/authZ | accounts created or reset by the admin must change password before use | pass | new receptionist's sign-in redirected to /password; other pages redirect there |
| hostile HTTP | negative Content-Length (-1) on POST /login, streaming 100-150 MiB | fail | server reads the socket until EOF and keeps it all: RSS 32 MiB -> 187 MiB (S1, below) |
| hostile HTTP | huge Content-Length (99999999999) | pass | 413 at once |
| hostile HTTP | non-numeric Content-Length ('abc') | fail | connection closed with no response; ValueError traceback printed to the service log (S5, below) |
| hostile HTTP | 10,000-level nested JSON body and malformed urlencoded body | pass | 400 (JSON is not parsed at all; the form has no CSRF token) |
| hostile HTTP | huge numeric ids in URLs (/patients/<25 digits>, /admin/practitioners/<23 digits>) | fail | 500 'Something went wrong' (no traceback in the page; OverflowError in the log) (S4, below) |
| hostile HTTP | negative and non-numeric ids (/patients/-1, /appt/abc) | pass | 404 |
| hostile HTTP | slow or idle connections (slowloris) against ThreadingHTTPServer without socket timeouts | not_checked | not tested for budget; the server sets no per-connection timeout and starts one thread per connection |
| injection | SQL injection: ' OR 1=1 -- in patient search and patient names | pass | parameterised queries; search returned 200 and treated the text literally |
| injection | stored and reflected XSS: <script> in patient first name and in the search query | pass | rendered HTML-escaped; raw <script> never appears in the page |
| injection | CSRF: signed-in POST without _csrf, and with a foreign Origin | pass | 400 'The form has expired'; cookies are also SameSite=Strict; probe test_sec_ok_2.py |
| injection | open redirect via next= on 'add patient' (and back= on appointment status) | fail | next=/\evil.com/x gives 'Location: /\evil.com/x?patient_id=1', which browsers follow to evil.com (S3, below) |
| injection | path traversal (/patients/../../etc/passwd) | pass | 404; no route takes a file name |
| authentication | repeated wrong passwords | pass | after 5 failures the account is locked for 15 minutes |
| authentication | session cookie flags | pass | fd_session: HttpOnly; SameSite=Strict; Path=/ (no Secure, correct for plain HTTP on localhost) |
| authentication | session ends on logout | pass | logout deletes the session row and clears the cookie |
| authentication | other sessions end on a password change | fail | a second admin session kept getting 200 on /day after the password was changed (S2, below) |
| authentication | admin password reset and deactivation end the user's sessions | pass | code deletes the user's sessions (domain.py:376, :392) |
| authentication | password storage | pass | PBKDF2-HMAC-SHA256, 240,000 rounds, random salt (domain.py:175) |
| secrets and defaults | default credentials and hard-coded secrets | pass | no default account; secret.key is generated randomly at first start with mode 600; grep found no hard-coded passwords or keys |
| secrets and defaults | passwords in logs | pass | the service log after sign-ins and password changes contained no passwords; request logging strips query strings |
| secrets and defaults | file permissions of the database | fail | data/frontdesk.db is created 644 (with the default umask the data directory is 755), so other local users can read it (S6, below) |
| dependencies | third-party dependencies | n/a | standard library only; no requirements file |
| error pages | bad ids, unknown routes, bad input | pass | friendly 404/400/500 pages with no traceback, file paths or SQL |

## Findings

| | severity | finding | status |
|---|---|---|---|
| S1 | high | A negative Content-Length makes the server read the whole connection into memory | fixed (a test checks it) |
| S2 | medium | Changing your password does not sign out your other sessions | fixed (a test checks it) |
| S3 | low | Open redirect through next= ('/\evil.com' passes the same-site check) | open |
| S4 | low | A very large id in a URL causes a 500 error | open |
| S5 | low | A non-numeric Content-Length drops the connection and logs a traceback | its test passes after other fixes; confirm by hand |
| S6 | low | The database (patient data, SMTP password) is readable by other users of the computer | open |

### S3 (low): Open redirect through next= ('/\evil.com' passes the same-site check)

- Where: frontdesk/web.py:642 (safe_next) and web.py:612 (back=)
- What happens: 303 with 'Location: /\evil.com/x?patient_id=1'; browsers treat '/\' like '//' and go to evil.com
- What should happen: only paths of the form /x (no backslash, no //) are followed; otherwise go to the patient page
- Reproduce: `POST /patients/new with next=/\evil.com/x (and a valid CSRF token)`
- Test: `tests/acceptance/test_next_redirect_after_adding_patient_only_goes_path_site.py` (marked as a known open item)

### S4 (low): A very large id in a URL causes a 500 error

- Where: frontdesk/web.py (int(pid) passed to SQLite, e.g. /patients/<id>, /admin/practitioners/<id>)
- What happens: 500 'Something went wrong' (no traceback shown; OverflowError logged)
- What should happen: 404 Not found
- Reproduce: `curl -b fd_session=... http://127.0.0.1:8080/patients/9999999999999999999999999`
- Test: `tests/acceptance/test_huge_numeric_id_url_gives_404_not_server_error.py` (marked as a known open item)

### S5 (low): A non-numeric Content-Length drops the connection and logs a traceback

- Where: frontdesk/web.py:1340
- What happens: no response; ValueError traceback in the service output
- What should happen: 400 Bad Request
- Reproduce: `printf 'POST /login HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\n\r\n' \| nc 127.0.0.1 8080`
- Test: `tests/acceptance/test_non_numeric_content_length_answered_400.py` passes since other fixes went in, but this finding wasn't repaired on its own: a changed default can also void the test's premise. Reproduce it by hand before closing it.

### S6 (low): The database (patient data, SMTP password) is readable by other users of the computer

- Where: frontdesk/app.py:76, frontdesk/db.py:157 (no umask/chmod on the data directory or database)
- What happens: frontdesk.db, -wal and -shm are 644 and data/ is 755 under a default umask; only secret.key is 600
- What should happen: data directory 700 and database files 600, like secret.key
- Reproduce: `python3 frontdesk.py; ls -l data/`
- Test: `tests/acceptance/test_database_holding_patient_data_smtp_password_readable_only.py` (marked as a known open item)

## Dependency audit

- Tool: pip-audit; result: no_dependencies.
- The product uses only the Python standard library (README, no requirements file); nothing to audit.

## Known limits

- This was a time-boxed review of v1 by one reviewer with the code and a running copy: scripted probes and manual checks, not a penetration test or an external audit.
- TLS is not provided; on a LAN the traffic (passwords, patient data) is plain HTTP unless a reverse proxy is added. Not tested.
- Slow or idle connections (slowloris) and thread exhaustion were not tested.
- The CLI backup/restore commands, backup file permissions and the outbox.log permissions were not checked in detail.
- Not every form field was fuzzed for XSS and SQL injection; patient name and search were tested, other fields were reviewed only by reading that output is passed through the escape helper.
- Account lockout is per username, so anyone who can reach the sign-in page can lock a known staff account for 15 minutes; this is the spec's design and was not ranked as a finding.

## Reporting a security issue

Please report security problems privately, not in a public issue: use the repository host's private vulnerability reporting (on GitHub: Security, then Report a vulnerability), or write to the maintainers directly. Include the version, the steps to reproduce and what an attacker could do. You will get an answer within a few working days.

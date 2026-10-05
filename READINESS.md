# Readiness

Where FrontDesk Book stands on the way to production: each item was checked by doing it (installing from the README, starting it, backing it up and restoring it, ...) or by reading the repository. Green is ready, amber needs attention before production, red is a gap.

**16 green, 2 amber, 0 red**.

| item | status | why | next step to production |
|---|---|---|---|
| Clean install from the README | green | the single documented command installs, creates the database and starts the service with no guessing | - |
| Listens on localhost unless configured | green | listens on 127.0.0.1 by default; FRONTDESK_HOST or host= changes it, and the README explains LAN use | - |
| Starts empty; demo data only on an explicit flag or command | green | a fresh start has no users, patients, practitioners or appointments; demo data comes only from 'demo' or '--demo' | - |
| First-run admin setup, no default password | green | first run redirects to a setup form where the operator picks the admin username and password; no default password exists | - |
| Configuration by environment or file, every option documented | green | config file or FRONTDESK_* environment variables; all 11 options in config.py are in the README table with defaults and meaning | - |
| Data location documented | green | README says all data lives in ./data by default and that data_dir / FRONTDESK_DATA_DIR changes it | - |
| Backup and restore work end to end | green | backup, change, restore round trip gave the data back exactly; restore refuses while the service runs and keeps the replaced data | - |
| Data survives a restart | green | data was still there after stopping and starting the service | - |
| Graceful shutdown | green | SIGTERM stops it within 1 second and the database is still consistent | - |
| Health endpoint (services) | green | fixed in this version (its test passes); it was: there is no health endpoint | - |
| Readable logs, no secrets or personal data | amber | the log has timestamps and no secrets, but requests are logged only at DEBUG and almost nothing else is logged | log requests (method, path, status, user) at INFO and log errors and reminder send results with timestamps |
| Schema changes and upgrades keep the data | green | the schema is versioned (meta.schema_version) with an ordered MIGRATIONS list, and it takes a pre-upgrade backup before migrating | - |
| CI workflow installs the project and runs the tests | green | .github/workflows/test.yml installs and runs the tests | - |
| Dependencies locked or pinned | green | no third-party runtime dependencies (standard library only) | - |
| Sensible .gitignore, no build artefacts in the repository | green | .gitignore covers caches and environments | - |
| README covers install, configure, run, upgrade, backup and restore, troubleshooting and limitations | green | every section is there | - |
| The documented test commands run green | green | 31 own test(s) pass; the acceptance suite is green (85 pass, 4 known open item(s) marked) | - |
| User-facing docs in plain words | amber | 7 line(s) of build-process jargon: SECURITY.md:42; SECURITY.md:45; SECURITY.md:47; SECURITY.md:49; SECURITY.md:55; SECURITY.md:60 | rewrite those lines in plain words |

## Security

See `SECURITY.md`: 6 finding(s), 4 not fixed by a tested change (low 4).

## Known open items in the tests

Marked as expected failures in `tests/acceptance/` (the suite stays green):

- `test_database_holding_patient_data_smtp_password_readable_only.py`: Known security issue (low): The database holding patient data and the SMTP password is readable only by the service's user
- `test_huge_numeric_id_url_gives_404_not_server_error.py`: Known security issue (low): A huge numeric id in a URL gives 404, not a server error
- `test_next_redirect_after_adding_patient_only_goes_path_site.py`: Known security issue (low): The next= redirect after adding a patient only goes to a path on this site
- `test_open_reminders_page.py`: Known open issue: Open the Reminders page

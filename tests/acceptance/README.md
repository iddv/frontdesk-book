# Acceptance tests

End-to-end checks of FrontDesk Book: 89 file(s), each checking one thing a user, an operator or an attacker could do, through the product's real interface. The helpers in `_helpers/` drive that interface.

Run them from the repository root (they need pytest):

    python -m pytest tests/acceptance

## Known open items

These tests are marked as expected failures (`xfail`): the behaviour they check isn't there yet, so the suite stays green. Each one passes (XPASS) once it is fixed; then delete the mark at the end of its file.

- `test_database_holding_patient_data_smtp_password_readable_only.py`: Known security issue (low): The database holding patient data and the SMTP password is readable only by the service's user
- `test_huge_numeric_id_url_gives_404_not_server_error.py`: Known security issue (low): A huge numeric id in a URL gives 404, not a server error
- `test_next_redirect_after_adding_patient_only_goes_path_site.py`: Known security issue (low): The next= redirect after adding a patient only goes to a path on this site
- `test_open_reminders_page.py`: Known open issue: Open the Reminders page

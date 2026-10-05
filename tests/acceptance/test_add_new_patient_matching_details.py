"""Add a new patient with matching details.

Expected: A duplicate warning is shown; nothing is created unless 'Create anyway' is chosen.
Source: "checks for likely duplicates ... Any match is shown with "Use existing" or "Create anyway"."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_add_new_patient_matching_details():
    s = System().basic()
    try:
        s.add_patient("Cara","Doe","c@example.com","07700 555123",dob="1980-01-01")
        for kw in (dict(email="z@example.com",phone="07999 111222",dob="1980-01-01"), dict(first="Q",email="z2@example.com",phone="07700 555123"), dict(first="R",email="c@example.com",phone="07999 333444")):
            first=kw.pop("first","Cara"); x,r=s.add_patient(first,"Doe",force=False,**kw); assert x is None or x==s.conn.execute("SELECT MIN(id) FROM patients WHERE last_name='Doe'").fetchone()[0]
            assert "Create anyway" in r.text, kw
    finally:
        s.close()

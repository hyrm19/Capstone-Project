# VitalityHub

A Flet school project for logging family exercise, steps, and water intake.
Accounts and activity history currently stay on this computer; Airtable syncing
has not been implemented yet.

## Run on Windows

From the project folder, using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe main.py
```

## Try authentication

1. Click **New here? Sign Up**.
2. Enter a display name, email, and a password of 8–128 characters. Confirm it.
3. After registration, log in with the same email and password.
4. Save **Steps: 2000** or **Water Intake: 3**.
5. Open **Personal** to see your own history and today's progress.
6. Click **Log Out**, register another member, and log in as them. Their Personal
   history should be separate; Family Timeline intentionally shows everyone's.
7. Close and reopen the app. Accounts and history remain, but login is required.

Email capitalization does not matter. Each activity check-in adds an amount, not
a cumulative daily total. The 8,000-step and 8-cup goals are demo targets, not
medical recommendations.

## Files and security limits

- `main.py`: startup, login/signup forms, and in-memory session control.
- `auth.py`: beginner-friendly signup and login logic, written as numbered steps.
- `account_helpers.py`: account JSON file handling and validation.
- `dashboard.py`: logging form, badges, tabs, and personal progress.
- `activities.py`: standard activities, units, and daily calculations.
- `storage.py`: activity JSON loading, validation, and safe file replacement.
- `data/members.json`: local accounts, including **plain-text passwords**.
- `data/habits.json`: local activity history.

The `data/` folder is ignored by Git. Back it up privately if needed; do not
publish it. Damaged files are reported rather than silently overwritten.

This is a **learning-only local login demo**, not a secure authentication service.
Passwords are saved as readable text, for example `"password": "demo1234"`.
**Use made-up passwords only. Never reuse a real password or publish this file.**
Anyone with access to the data files can read or modify them. Activity history
is not encrypted. There is no email verification, password recovery, or account
sharing across computers yet. Restarting the app always starts logged out.

Login compares the typed password directly with the saved `password` string.
Password inputs remain masked in the interface (`password=True`); masking does
not encrypt the JSON file. Login never changes the account file. Hash-based
accounts and automatic conversion are no longer supported. Real deployment
would require replacing this plain-text approach with proper password storage.

Historical demo entries keep their original member IDs; registering with the
same display name does not claim those entries. Older entries without an owner
or unit retain those uncertainties.

## Run automated tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use temporary files and do not modify your real accounts or history.

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
- `auth.py`: account validation and PBKDF2-SHA256 password verification, using
  random salts and 600,000 iterations. Plain-text passwords are not saved.
- `dashboard.py`: logging form, badges, tabs, and personal progress.
- `activities.py`: standard activities, units, and daily calculations.
- `storage.py`: activity JSON loading, validation, and safe file replacement.
- `data/members.json`: local accounts, including password hashes.
- `data/habits.json`: local activity history.

The `data/` folder is ignored by Git. Back it up privately if needed; do not
publish it. Damaged files are reported rather than silently overwritten.

This is a **local desktop authentication demo**, not a hosted security service.
Anyone with access to the data files can read or modify them. Activity history
is not encrypted. There is no email verification, password recovery, or account
sharing across computers yet. Restarting the app always starts logged out.

Historical demo entries keep their original member IDs; registering with the
same display name does not claim those entries. Older entries without an owner
or unit retain those uncertainties.

## Run automated tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use temporary files and do not modify your real accounts or history.

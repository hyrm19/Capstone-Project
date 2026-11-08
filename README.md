# VitalityHub — cloud-only desktop demo

A Flet school project for family exercise, steps, and water intake. The app runs
as a desktop window, but **Airtable is the only account and activity database**.
There is no local JSON database, offline queue, or remembered login. Internet
access is required to register, log in, load history, and save an activity.

## 1. Configure Airtable

Use one base with two separate tables. Column names are case-sensitive.

### `Habits` — activity history

| Column | Airtable type |
| --- | --- |
| `LogID` | Single line text — primary field |
| `MemberID` | Single line text |
| `MemberName` | Single line text |
| `Activity` | Single line text |
| `Value` | Number, allowing decimals |
| `Unit` | Single line text |
| `LoggedAt` | Date, with time enabled |

### `Members` — demo accounts

All five columns below are **Single line text**. Use lowercase names exactly:

| Column | Purpose |
| --- | --- |
| `id` | Primary field; the app generates a `member-...` ID during signup |
| `name` | Display name |
| `email` | Login email |
| `password` | Plain-text DEMO password |
| `color` | Badge color such as `#2563EB` |

The Members `id` column is your app's member ID, not Airtable's `rec...` record
identifier. Do not create duplicate IDs or emails. Airtable does not enforce
unique emails across computers, so this simple signup is not production-ready.
Completely empty starter rows are ignored.

Give a Personal Access Token `data.records:read` and `data.records:write` scopes,
restricted to this base. Keep the token in the private `.env` beside `main.py`:

```dotenv
AIRTABLE_TOKEN=your_personal_access_token_here
AIRTABLE_BASE_ID=appYourBaseIdHere
AIRTABLE_TABLE_NAME=Habits
AIRTABLE_MEMBERS_TABLE=Members
```

If your account table has another name, change `AIRTABLE_MEMBERS_TABLE`.
`.env` is configuration, not an account/history database, and remains excluded
from Git. Never share it. `.env.example` contains only placeholders.

## 2. Run

From the project folder, using your existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

1. Choose **Sign Up**. The app checks online emails and creates a Members row.
2. Log in. Your password is compared as a normal string against the online row.
3. The dashboard automatically loads Habits. Saving is enabled after history
   has loaded successfully.
4. Log **Steps: 2000** or **Water Intake: 3**. Save Log writes directly to
   Airtable; only a confirmed save clears the form and updates the views.
5. **Family Timeline** shows everyone's records. **Personal** filters by your
   exact MemberID and shows today's steps/water progress.
6. **Cloud Status → Refresh from Airtable** reloads all pages and reflects cloud
   additions, edits, and deletions. Test Connection is a separate read-only check.
7. Log out or close the app. A future login downloads fresh cloud data.

Each log adds an amount, not a cumulative total. For example, after logging 2,000
steps, log 1,000 more when you reach 3,000. The goals of 8,000 steps and 8 cups
are demo targets, not medical recommendations.

## What happens without internet?

- Login and signup cannot succeed using old local files.
- A failed initial history download leaves Save Log disabled. Try Refresh again.
- A later failed refresh keeps only the last in-memory view for this session.
- A failed save keeps the form filled. Keep the app open and retry: the same
  in-memory LogID updates the same cloud row rather than creating a duplicate.
- A request may reach Airtable even if its response is lost. Refresh to check
  before re-entering an activity after restarting. Draft IDs and unsaved input
  are not persisted when the app closes.

Blank, invalid, and duplicate-LogID cloud rows are skipped with counts. Unknown
historical units stay unspecified. Member names on activities can supply badges
but do not create accounts or claim another person's history.

## Security limits — learning demo only

Passwords are **plain text in Airtable**, as requested for this learning stage.
The password inputs start masked and have an eye button to show/hide text. Masking does
not protect the database. Anyone with the desktop app's Airtable token can read
the Members table and modify records; this is not real access-control security.

**Use made-up passwords only. Do not distribute real tokens or real accounts.**
Account passwords are sent only to Members during signup, never to Habits.
Login reads accounts for the simple comparison. There is no email verification,
password reset, password hashing, or server-enforced per-user authorization.

Old `data/members.json` and `data/habits.json` files, if present, are left
untouched and unused. They are not automatically uploaded or deleted. Existing
cloud activity records keep their original MemberIDs; registering the same
display name does not reassign them to a new account.

## Source files

- `main.py`: app startup, async login/signup forms, and in-memory sessions.
- `auth.py`: simple online account validation and string password comparison.
- `dashboard.py`: activity input, cloud save/refresh, tabs, badges, and progress.
- `airtable_api.py`: private configuration and Airtable HTTP requests.
- `cloud_history.py`: validates rows and sorts the temporary display.
- `activities.py`: names, units, demo goals, and daily total calculations.
- `tests/`: isolated tests using fake cloud responses, never your real tables.

The old local-storage modules were removed. Flet/Python may still generate
framework/cache files; account and activity records are not saved in them by
this app. The unrelated `lecture-review/` folder is left untouched.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

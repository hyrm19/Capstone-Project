"""Learning-only local login with readable passwords, NOT for real accounts."""

from uuid import uuid4

# These helpers handle the technical details. You do not need to understand
# temporary files to follow the signup/login steps below.
from account_helpers import (
    ACCOUNT_LOCK, BADGE_COLORS, MEMBERS_FILE, AccountError, AccountFile,
    normalize_email,
)


def public_member(account):
    """Take only the information that the dashboard needs from an account."""
    return {
        "id": account["id"],
        "name": account["name"],
        "email": account["email"],
        "color": account["color"],
    }


class AccountStore:
    """An object that groups the account functions used by main.py."""

    def __init__(self, path=MEMBERS_FILE):
        # __init__ runs when main.py creates AccountStore(). "self" means this
        # particular object. Remember its file so all methods use the same data.
        self.file = AccountFile(path)
        self.path = self.file.path

    def members(self):
        """Get the family members' names and colors for activity badges."""
        accounts = self.file.load()
        members = []
        for account in accounts:
            members.append(public_member(account))
        return members

    def register(self, name, email, password):
        """SIGN UP: check input, check duplicates, create an account, save it."""
        # 1. Check the input. strip() removes unwanted spaces around the name.
        # Raising AccountError stops this function; main.py displays the message.
        name = name.strip()
        if len(name) < 1 or len(name) > 60:
            raise AccountError("Enter a display name between 1 and 60 characters.")
        email = normalize_email(email)  # " Alex@Example.com " -> "alex@example.com"
        if len(password) < 8 or len(password) > 128 or password.strip() == "":
            raise AccountError("Use a password of 8–128 characters, not just spaces.")

        # The helper lock simply makes overlapping signup attempts take turns.
        with ACCOUNT_LOCK:
            # 2. Look through existing accounts for the same email.
            accounts = self.file.load()
            for account in accounts:
                if account["email"] == email:
                    raise AccountError("An account with this email already exists.")

            # 3. Build a dictionary for the new member. uuid4 creates a unique
            # ID, so two people with the same name still have separate histories.
            # % cycles through badge colors: 0, 1, 2, 3, 4, then back to 0.
            color_index = len(accounts) % len(BADGE_COLORS)
            new_account = {
                "id": "member-" + uuid4().hex,
                "name": name,
                "email": email,
                "color": BADGE_COLORS[color_index],
                # Learning demo only: save exactly what the user typed.
                # Anyone opening members.json can read this password, so never
                # use a real password or publish this data file.
                "password": password,
            }

            # 4. Add the account and save the whole list. Only return success
            # after the file helper has finished writing it to disk.
            accounts.append(new_account)
            self.file.save(accounts)
            return public_member(new_account)

    def authenticate(self, email, password):
        """LOG IN: find the email, check its password, return that member."""
        error_message = "Incorrect email or password."

        # 1. Check the input. Invalid emails and incorrect passwords use the
        # same message. Password spaces are not removed: they can be intentional.
        try:
            email = normalize_email(email)
        except AccountError:
            raise AccountError(error_message) from None
        if len(password) < 1 or len(password) > 128:
            raise AccountError(error_message)

        # 2. Read the saved accounts and check them one at a time.
        # Login only reads this file; it does not change or convert passwords.
        accounts = self.file.load()
        for account in accounts:
            if account["email"] == email:
                # 3. Compare two ordinary strings. == means "is equal to".
                # Passwords must match exactly, including capitals and spaces.
                if account["password"] == password:
                    # 4. Return display information, never the password.
                    # main.py opens the dashboard and manages logout.
                    return public_member(account)

        # No account matched both the email and password, so login failed.
        raise AccountError(error_message)

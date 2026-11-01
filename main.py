"""Start VitalityHub and control which screen the current session may access."""

import flet as ft

from auth import AccountError, AccountStore
from dashboard import build_dashboard


def main(page: ft.Page):
    page.title = "VitalityHub | Family Activities"
    page.bgcolor = "#0B0C10"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 24
    accounts = AccountStore()

    # These values exist only in this Page's memory. Closing/reopening the app
    # starts logged out: no password or automatic-login token is saved to disk.
    session_token = None
    screen_token = None

    def log_out(token):
        # nonlocal lets this nested function change the session_token belonging
        # to main(), instead of creating a different local variable with its name.
        nonlocal session_token
        # A delayed logout from a previous screen must not end a newer session.
        if session_token is not token:
            return
        session_token = None
        show_auth(message="You have been logged out.")

    def show_dashboard(member):
        nonlocal session_token, screen_token
        # Load only display-safe profiles, then mint a new identity for THIS
        # login session. Checking just a member ID would let old handlers become
        # active again if the same person logged out and logged back in.
        members = {profile["id"]: profile for profile in accounts.members()}
        token = object()
        session_token = token
        screen_token = token
        page.clean()
        build_dashboard(
            page,
            current_member=member,
            members=members,
            is_session_active=lambda: session_token is token,
            on_logout=lambda e: log_out(token),
        )
        page.update()

    def show_auth(sign_up=False, message="", email_value=""):
        nonlocal screen_token, session_token
        session_token = None
        token = object()
        screen_token = token
        busy = False

        # Build fresh controls whenever the form changes. Password text is never
        # carried from Signup to Login or from one user's session to another.
        name = ft.TextField(label="Display name", visible=sign_up, max_length=60, data="auth_name")
        email = ft.TextField(
            label="Email", value=email_value,
            keyboard_type=ft.KeyboardType.EMAIL, data="auth_email",
        )
        password = ft.TextField(
            label="Password (8–128 characters)" if sign_up else "Password",
            password=True, can_reveal_password=True, data="auth_password",
        )
        confirm = ft.TextField(
            label="Confirm password", password=True, can_reveal_password=True,
            visible=sign_up, data="auth_confirm",
        )
        feedback = ft.Text(message, color="#66FCF1", visible=bool(message), data="auth_feedback")
        spinner = ft.ProgressRing(width=24, height=24, visible=False, data="auth_spinner")

        def set_busy(value):
            # Password hashing deliberately takes work, so show progress and
            # prevent duplicate submissions or form switches while it runs.
            nonlocal busy
            busy = value
            spinner.visible = value
            for control in (name, email, password, confirm, submit_button, switch_button):
                control.disabled = value
            page.update()

        def submit(e):
            if screen_token is not token or busy:
                return
            feedback.visible = False
            confirm.error_text = None
            if sign_up and password.value != confirm.value:
                confirm.error_text = "Passwords do not match."
                page.update()
                return
            set_busy(True)
            try:
                if sign_up:
                    member = accounts.register(name.value or "", email.value or "", password.value or "")
                    # Require a real login after registration instead of keeping
                    # the registration password around or auto-selecting a user.
                    password.value = confirm.value = ""
                    show_auth(message="Account created. Please log in.", email_value=member["email"])
                else:
                    member = accounts.authenticate(email.value or "", password.value or "")
                    password.value = confirm.value = ""
                    show_dashboard(member)
            except AccountError as error:
                # This includes validation, damaged files, and failed writes.
                # No successful authentication means no access to the dashboard.
                password.value = confirm.value = ""
                feedback.value = str(error)
                feedback.color = "#FCA5A5"
                feedback.visible = True
            finally:
                # Do not update old controls after replacing the entire screen.
                if screen_token is token:
                    set_busy(False)

        def switch_form(e):
            if screen_token is token and not busy:
                password.value = confirm.value = ""
                show_auth(sign_up=not sign_up)

        submit_button = ft.Button(
            "Sign Up" if sign_up else "Log In", on_click=submit,
            bgcolor="#66FCF1", color="#0B0C10", height=46,
            width=float("inf"), data="submit_auth",
        )
        switch_button = ft.Button(
            "Already have an account? Log In" if sign_up else "New here? Sign Up",
            on_click=switch_form, data="switch_auth",
        )
        # data labels above are stable identifiers used by our interface tests;
        # they do not contain credentials and are not part of authentication.
        page.clean()
        page.add(
            ft.Container(
                width=440,
                bgcolor="#1F2833",
                padding=24,
                border_radius=16,
                content=ft.Column(
                    controls=[
                        ft.Text("VitalityHub", size=28, weight="bold", color="#66FCF1"),
                        ft.Text("Create a family account" if sign_up else "Welcome back", size=20),
                        ft.Text(
                            "Local accounts on this computer only. Anyone with access "
                            "to the data files can read or modify them; this is not "
                            "a hosted authentication service.", size=12, color="#8D8D8D",
                        ),
                        name, email, password, confirm, feedback, spinner,
                        submit_button, switch_button,
                    ],
                    tight=True, spacing=12, scroll=ft.ScrollMode.AUTO,
                ),
            )
        )
        page.update()

    # The app always opens at Login. The dashboard is constructed only after
    # authenticate() has checked the supplied password against its stored hash.
    show_auth()


if __name__ == "__main__":
    ft.run(main)

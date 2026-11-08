"""Start VitalityHub and control which screen the current session may access."""

import asyncio

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

    async def show_dashboard(member):
        nonlocal session_token, screen_token
        # Load only display-safe profiles, then mint a new identity for THIS
        # login session. Checking just a member ID would let old handlers become
        # active again if the same person logged out and logged back in.
        profiles = await asyncio.to_thread(accounts.members)
        members = {profile["id"]: profile for profile in profiles}
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
        def make_password_field(label, key, visible=True):
            # Use a custom suffix rather than Flet's built-in reveal button.
            # Our icon represents the CURRENT STATE: crossed eye = hidden,
            # open eye = visible. It does not represent the next click's action.
            field = ft.TextField(
                label=label, password=True, can_reveal_password=False,
                visible=visible, data=key,
                # Match the email field's original sizing. Only the suffix eye
                # is different; do not shrink the password text or padding.
                dense=email.dense, text_size=email.text_size,
                content_padding=email.content_padding,
            )
            eye = ft.IconButton(
                icon=ft.Icons.VISIBILITY_OFF, tooltip="Show password",
                data=key + "_eye",
                # A large default suffix button can stretch the whole input.
                icon_size=20, width=36, height=36, padding=6,
            )

            def toggle_password(e):
                # Ignore old screen events and changes during a login request.
                if screen_token is not token or busy:
                    return
                field.password = not field.password
                eye.icon = ft.Icons.VISIBILITY_OFF if field.password else ft.Icons.VISIBILITY
                eye.tooltip = "Show password" if field.password else "Hide password"
                page.update()

            eye.on_click = toggle_password
            field.suffix = eye
            return field

        password = make_password_field(
            "Password (8–128 characters)" if sign_up else "Password", "auth_password"
        )
        confirm = make_password_field("Confirm password", "auth_confirm", visible=sign_up)
        feedback = ft.Text(message, color="#66FCF1", visible=bool(message), data="auth_feedback")
        spinner = ft.ProgressRing(width=24, height=24, visible=False, data="auth_spinner")

        def set_busy(value):
            # Show progress during cloud account requests and prevent duplicate
            # submissions while they run.
            nonlocal busy
            busy = value
            spinner.visible = value
            for control in (name, email, password, confirm, submit_button, switch_button):
                control.disabled = value
            page.update()

        async def submit(e):
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
                    member = await asyncio.to_thread(
                        accounts.register, name.value or "", email.value or "", password.value or ""
                    )
                    if screen_token is not token:
                        return
                    # Require a real login after registration instead of keeping
                    # the registration password around or auto-selecting a user.
                    password.value = confirm.value = ""
                    show_auth(message="Account created. Please log in.", email_value=member["email"])
                else:
                    member = await asyncio.to_thread(accounts.authenticate, email.value or "", password.value or "")
                    if screen_token is not token:
                        return
                    password.value = confirm.value = ""
                    await show_dashboard(member)
            except AccountError as error:
                # This includes validation, table setup, and network failures.
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
                            "Learning demo only: passwords are saved as readable text "
                            "in Airtable. Anyone with the app's token can read them. "
                            "Use made-up passwords only. Internet is required.",
                            size=12, color="#FBBF24",
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
    # authenticate() has compared the supplied password with the saved password.
    show_auth()


if __name__ == "__main__":
    ft.run(main)

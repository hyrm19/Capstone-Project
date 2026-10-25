# datetime gives each saved activity a local date and time.
from datetime import datetime
# isfinite rejects special numeric values such as infinity and NaN (not a number).
from math import isfinite

# Flet provides the interface controls. "ft" is a shorter name for the module.
import flet as ft

def main(page: ft.Page):
    # Flet calls main() with the Page that contains this app's interface.
    page.title = "VitalityHub | Premium Capstone"
    page.bgcolor = "#0B0C10" 
    page.padding = 24
    # Store activity dictionaries in memory for this page session.
    # This is NOT file or cloud storage: closing the app loses these entries.
    habits = []

    def make_header():
        # Build and return the header control; page.add() displays it later.
        # A Container adds decoration, while its Row places children side by side.
        return ft.Container(
            gradient=ft.LinearGradient(
                colors=["#1F2833", "#45A29E"],
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT
            ),
            padding=20,
            border_radius=16,
            border=ft.Border.all(1, "#45A29E"),
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.FITNESS_CENTER, color="#34D399", size=32),
                    ft.Text("VitalityHub", size=22, weight="bold", color="white"),
                ],
                spacing=12,
            ),
        )

    # Reserved for the future AutoComplete feature; not used by the form yet.
    exercise_options = ["Running", "Swimming", "Cycling", "Yoga", "Water Intake", "Gym"]

    # Keep references to the input controls so save_log() can read their .value,
    # show validation messages through .error_text, and clear them after a save.
    activity_name = ft.TextField(
        label="Activity Name", color="white", border_color="#45A29E"
    )
    activity_value = ft.TextField(
        label="Value (Distance / Cups / Mins)",
        color="white",
        border_color="#45A29E",
        # Requests a numeric keyboard on supported devices. Users can still
        # enter invalid text, so save_log() must validate the value itself.
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    # Show this placeholder until the first valid activity has been saved.
    empty_state = ft.Column(
        controls=[
            ft.Icon(ft.Icons.DIRECTIONS_RUN, size=48, color="#66FCF1"),
            ft.Text("No activities logged yet.", color="#8D8D8D"),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
    )
    # ListView makes the entries scrollable. It starts hidden because it is empty.
    # expand=True lets it use the available vertical space in its parent Column.
    activity_list = ft.ListView(expand=True, spacing=12, visible=False)

    def save_log(e):
        # Flet passes a click event as e. We do not need its details in this step.
        # This nested function can access the fields, habits, and page created
        # inside main(), without making those variables global.

        # Empty fields may contain None; "or ''" turns that into a safe string.
        # strip() removes surrounding spaces, so spaces alone are not a name.
        name = (activity_name.value or "").strip()
        raw_value = (activity_value.value or "").strip()
        # Reset old error messages on each attempt. None removes an error.
        # The conditional expression sets a name error only when name is empty.
        activity_name.error_text = None if name else "Enter an activity name."
        activity_value.error_text = None

        try:
            # float() accepts whole numbers and decimals, such as 5 and 2.5.
            # It raises ValueError for input such as an empty string or "hello".
            value = float(raw_value)
            # float() also accepts "nan" and "inf", so check those explicitly.
            # For this simple activity form, zero and negative values are invalid.
            if not isfinite(value) or value <= 0:
                # Send these invalid numbers to the same error handler below.
                raise ValueError
        except ValueError:
            activity_value.error_text = "Enter a number greater than zero."

        if activity_name.error_text or activity_value.error_text:
            # Refresh the interface to display the errors, then stop early.
            # Nothing is saved and the user's input remains available to fix.
            page.update()
            return

        # A dictionary groups the data for one activity under meaningful keys.
        # Only validated values reach this point. datetime.now() uses local time.
        habit = {
            "name": name,
            "value": value,
            "logged_at": datetime.now(),
        }
        # Save the data separately from the visual controls that display it.
        habits.append(habit)
        # Insert the card at index 0 (the start) so the newest entry appears first.
        # habits keeps save order; activity_list keeps the visual newest-first order.
        activity_list.controls.insert(
            0,
            ft.Container(
                bgcolor="#0B0C10",
                padding=16,
                border_radius=10,
                content=ft.Column(
                    controls=[
                        ft.Text(habit["name"], weight="bold", color="white"),
                        # The f-string inserts the number into the label.
                        # :g uses compact formatting, e.g. 5 instead of 5.0.
                        ft.Text(f"Value: {habit['value']:g}", color="#66FCF1"),
                        ft.Text(
                            # Format the datetime as readable text, for example
                            # "25 Oct 2026, 14:30" (day, month, year, 24-hour time).
                            habit["logged_at"].strftime("%d %b %Y, %H:%M"),
                            size=12,
                            color="#8D8D8D",
                        ),
                    ],
                    spacing=4,
                ),
            ),
        )
        # Replace the placeholder with the list after a successful save.
        empty_state.visible = False
        activity_list.visible = True
        # Clear the form for the next entry. Validation errors are already None.
        activity_name.value = ""
        activity_value.value = ""
        # Send all the changed controls to the interface in one update.
        page.update()
    
    # The left-hand card holds the form. Column stacks its children vertically.
    input_card = ft.Container(
        bgcolor="#1F2833",
        width=340,
        padding=20,
        border_radius=16,
        border=ft.Border.all(1, "#45A29E"),
        content=ft.Column(
            controls=[
                ft.Text("Log New Activity", size=16, weight="bold", color="white"),
                ft.Divider(height=10, color="#0B0C10"),
                activity_name,
                activity_value,
                ft.Button(
                    "Save Log",
                    icon=ft.Icons.SAVE_OUTLINED,
                    bgcolor="#66FCF1",
                    color="#0B0C10",
                    # Fill the card's available width, but keep a fixed height.
                    # expand=True here would stretch vertically inside the Column.
                    width=float("inf"),
                    height=46,
                    # Pass the function itself, not save_log(): Flet should call
                    # it when clicked, rather than while building the interface.
                    on_click=save_log,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                )
            ],
            # Keep the form Column only as tall as its contents need.
            tight=True,
            spacing=12,
        ),
    )

    # Right-hand panel: tab navigation above the activity display.
    # The tabs are currently placeholders; separate tab views come in a later step.
    data_panel = ft.Column(
        controls=[
            ft.Tabs(
                selected_index=0,
                animation_duration=300,
                length=3,
                content=ft.TabBar(
                    tabs=[
                        ft.Tab(label="Family Timeline", icon=ft.Icons.DASHBOARD_OUTLINED),
                        ft.Tab(label="Personal Logs", icon=ft.Icons.PERSON_OUTLINED),
                        ft.Tab(label="Cloud Status", icon=ft.Icons.CLOUD_SYNC_OUTLINED),
                    ],
                )
            ),
            ft.Container(
                bgcolor="#1F2833",
                padding=20,
                border_radius=16,
                border=ft.Border.all(1, "#45A29E"),
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    # Both controls stay in the layout definition, but their
                    # visible properties decide which one the user can see.
                    controls=[empty_state, activity_list],
                    expand=True,
                ),
            ),
        ],
        expand=True,
        spacing=12,
    )

    # Attach the finished controls to the page: header, spacer, then a Row
    # containing the input card on the left and the data panel on the right.
    page.add(
        make_header(),
        ft.Divider(height=15, color="transparent"),
        ft.Row(
            controls=[input_card, data_panel],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
            expand=True,
        ),
    )

# Start Flet and let it call main() to build the page.
ft.run(main)

"""Activity forms and tab views for an already authenticated page session."""

# datetime gives each saved activity a local date and time.
from datetime import datetime
# isfinite rejects special numeric values such as infinity and NaN (not a number).
from math import isfinite

# Flet provides the interface controls. "ft" is a shorter name for the module.
import flet as ft

from activities import (
    ACTIVITY_UNITS, DEMO_STEP_GOAL, DEMO_WATER_GOAL,
    canonical_activity, daily_totals,
)

# File handling lives in a separate module so the interface stays readable.
from storage import DATA_FILE, StorageError, load_habits, save_habits

# Keep old demo identities ONLY for displaying historical entries. They cannot
# log in, and a newly registered account never inherits one of these IDs.
DEMO_MEMBERS = {
    "demo-alex": {"name": "Alex Morgan", "color": "#2563EB"},
    "demo-jamie": {"name": "Jamie Morgan", "color": "#7C3AED"},
    "demo-sam": {"name": "Sam Morgan", "color": "#047857"},
}


def member_details(member_id, members):
    """Look up badge information without assigning unknown or old entries."""
    member = members.get(member_id) or DEMO_MEMBERS.get(member_id)
    if member is None:
        # An unknown ID is different from an old entry with no owner at all.
        return {
            "name": "Unknown member" if member_id else "Unassigned",
            "color": "#4B5563",
            "initials": "?",
        }
    # Split a name into words and take the first letter of the first two words.
    # For example, "Alex Morgan" becomes "AM". upper() capitalizes the letters.
    initials = "".join(word[0] for word in member["name"].split()[:2]).upper()
    return {**member, "initials": initials}


def build_dashboard(page, current_member, members, is_session_active, on_logout):
    """Build the dashboard only for the authenticated session supplied by main."""
    # main.py owns login state. This callback also protects stale event handlers
    # after logout: an old Save Log button must not keep writing as the old user.
    if not is_session_active():
        return
    member_id = current_member["id"]
    # Restore the saved history before building the interface. If loading fails,
    # keep the original file untouched and block saves until it is repaired.
    load_error = None
    try:
        habits = load_habits()
    except StorageError as error:
        habits = []
        load_error = str(error)

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
                    ft.Container(expand=True),
                    ft.Button("Log Out", on_click=on_logout, data="logout"),
                ],
                spacing=12,
            ),
        )

    # AutoComplete filters these suggestions as the user types. Its .value is
    # still plain text, so saving must validate it even if no suggestion was
    # clicked. The key is used for matching; value is the displayed activity name.
    activity_name = ft.AutoComplete(
        suggestions=[
            ft.AutoCompleteSuggestion(key=name, value=name)
            for name in ACTIVITY_UNITS
        ],
        suggestions_max_height=200,
    )
    # Unlike TextField, AutoComplete has no error_text property in this Flet
    # version. Place a separate error label directly beneath it instead.
    activity_name_error = ft.Text(color="#FCA5A5", size=12, visible=False)
    activity_value = ft.TextField(
        label="Value (choose an activity first)",
        color="white",
        border_color="#45A29E",
        # Requests a numeric keyboard on supported devices. Users can still
        # enter invalid text, so save_log() must validate the value itself.
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    def update_value_label():
        # Derive the unit from the CURRENT text, not a previous suggestion.
        # This prevents choosing Running, editing it to Yoga, and keeping km.
        name = canonical_activity(activity_name.value)
        unit = ACTIVITY_UNITS.get(name)
        activity_value.label = f"Value ({unit})" if unit else "Value (choose an activity first)"
        activity_value.helper_text = (
            "Enter additional whole-number steps, not your daily total."
            if name == "Steps" else
            "Enter cups to add to today's total."
            if name == "Water Intake" else None
        )

    def change_activity(e):
        # on_change runs for typing; show the matching unit as soon as the name
        # is recognized. Validation errors disappear while the user corrects it.
        activity_name_error.value = ""
        activity_name_error.visible = False
        activity_value.error_text = None
        update_value_label()
        page.update()

    def select_activity(e):
        # on_select includes the suggestion itself. Explicitly copy its text
        # into .value so both clicking and typing use the same save path.
        activity_name.value = e.selection.value
        change_activity(e)

    activity_name.on_change = change_activity
    activity_name.on_select = select_activity
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

    # Use an inline message for storage errors so they remain visible.
    storage_status = ft.Text(
        value=(
            f"{load_error}\nSaving is disabled to protect your history. "
            "Back up and repair the file, then restart the app."
            if load_error else ""
        ),
        color="#FCA5A5",
        visible=load_error is not None,
    )

    # Each tab owns its own controls. Do not put the same Text control into two
    # views: controls have one place in the interface, even if their text matches.
    personal_summary = ft.Text(color="#66FCF1")
    personal_name = ft.Text(size=18, weight="bold", color="white")
    personal_avatar = ft.CircleAvatar(radius=24, color="white")
    personal_empty = ft.Text(color="#8D8D8D")
    # Personal now scrolls as one page (profile + progress + history). Use a
    # normal Column for its cards instead of nesting an expanding ListView
    # inside an unlimited scrolling parent. Family keeps its own ListView.
    personal_list = ft.Column(tight=True, spacing=12)
    progress_date = ft.Text(weight="bold", color="white")
    steps_label = ft.Text(color="white")
    water_label = ft.Text(color="white")
    # ProgressBar expects a fraction from 0 to 1, not a percentage from 0 to 100.
    steps_bar = ft.ProgressBar(value=0, color="#66FCF1", bgcolor="#0B0C10")
    water_bar = ft.ProgressBar(value=0, color="#60A5FA", bgcolor="#0B0C10")
    daily_progress_panel = ft.Column(
        controls=[
            progress_date,
            ft.Text(
                f"Demo goals: {DEMO_STEP_GOAL:,} steps and {DEMO_WATER_GOAL:g} cups "
                "— not medical recommendations.",
                size=12,
                color="#8D8D8D",
            ),
            steps_label,
            steps_bar,
            water_label,
            water_bar,
            ft.Text(
                "Each check-in adds to today's total. Older entries without units are excluded.",
                size=12,
                color="#8D8D8D",
            ),
        ],
        spacing=8,
        tight=True,
    )
    cloud_summary = ft.Text(color="white")
    local_storage_health = ft.Text(
        "Local storage needs attention." if load_error else "Local JSON storage is ready.",
        color="#FCA5A5" if load_error else "#66FCF1",
    )

    def refresh_summaries():
        # Read the same in-memory history used by the timeline. Recalculate after
        # a successful save so the other tabs update without restarting the app.
        # Personal always follows the signed-in member, never a user-editable
        # dropdown. Public member details contain no passwords or password hashes.
        member = member_details(member_id, members)
        personal_name.value = member["name"]
        personal_avatar.bgcolor = member["color"]
        personal_avatar.content = ft.Text(member["initials"], color="white")
        # A damaged file means totals are unknown, NOT zero. Hide the progress
        # section and let the existing load-error message explain the problem.
        daily_progress_panel.visible = load_error is None
        if load_error:
            personal_summary.value = "History unavailable: the local file could not be loaded."
            cloud_summary.value = "Saved activity count unavailable."
            personal_list.controls = []
            personal_list.visible = False
            personal_empty.visible = False
            return
        # Match stable IDs, NOT names. Old unassigned records cannot accidentally
        # become the signed-in member's records because their ID is missing.
        member_habits = [
            habit for habit in habits
            if habit.get("member_id") == member_id
        ]
        personal_summary.value = f"Activities for {member['name']}: {len(member_habits)}"
        today = datetime.now().date()
        totals = daily_totals(habits, member_id, today=today)
        progress_date.value = f"Today's progress — {today.strftime('%d %b %Y')}"
        step_ratio = totals["steps"] / DEMO_STEP_GOAL
        water_ratio = totals["cups"] / DEMO_WATER_GOAL
        # Keep actual totals and percentages visible above the goal, but stop
        # the bars at 100%: Flet's visual range is only 0 through 1.
        steps_label.value = (
            f"Steps: {totals['steps']:,} / {DEMO_STEP_GOAL:,} "
            f"({step_ratio * 100:g}%)"
        )
        water_label.value = (
            f"Water: {totals['cups']:g} / {DEMO_WATER_GOAL:g} cups "
            f"({water_ratio * 100:g}%)"
        )
        steps_bar.value = min(step_ratio, 1.0)
        water_bar.value = min(water_ratio, 1.0)
        # Build separate cards for Personal; a single Flet control must not be
        # shared between both tab pages, even if it shows the same activity.
        personal_list.controls = [
            make_activity_card(habit) for habit in reversed(member_habits)
        ]
        personal_list.visible = bool(member_habits)
        personal_empty.value = f"No activities for {member['name']} yet."
        personal_empty.visible = not member_habits
        cloud_summary.value = f"Activities loaded on this device: {len(habits)}"

    def make_activity_card(habit):
        # Reuse the same card for activities loaded from disk and newly saved ones.
        member = member_details(habit.get("member_id"), members)
        return ft.Container(
            bgcolor="#0B0C10",
            padding=16,
            border_radius=10,
            content=ft.Row(
                controls=[
                    # CircleAvatar makes the colored badge; Text supplies initials.
                    # The full name stays visible too, so color is not the only
                    # way to identify the person who recorded this activity.
                    ft.CircleAvatar(
                        content=ft.Text(member["initials"], color="white"),
                        bgcolor=member["color"],
                        radius=20,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(member["name"], size=12, color="#8D8D8D"),
                            ft.Text(habit["name"], weight="bold", color="white"),
                            # :g uses compact formatting, e.g. 5 instead of 5.0.
                            # Missing units belong to older records. Keep that
                            # uncertainty visible instead of guessing a unit.
                            ft.Text(
                                f"Value: {habit['value']:g} {habit.get('unit', '(unit unspecified)')}",
                                color="#66FCF1",
                            ),
                            ft.Text(
                                habit["logged_at"].strftime("%d %b %Y, %H:%M"),
                                size=12,
                                color="#8D8D8D",
                            ),
                        ],
                        expand=True,
                        spacing=4,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=12,
            ),
        )

    # Call this only after make_activity_card is defined: Python must know the
    # helper before refresh_summaries() can use it to create Personal's cards.
    refresh_summaries()

    # The file stores save order (oldest first). Reverse it for the display.
    activity_list.controls = [make_activity_card(habit) for habit in reversed(habits)]
    activity_list.visible = bool(habits)
    # A load failure is not the same as having no history: show the warning instead.
    empty_state.visible = not habits and load_error is None

    def save_log(e):
        # Flet passes a click event as e. We do not need its details in this step.
        # This nested function can access the fields, habits, and page created
        # inside build_dashboard(), without making those variables global.

        # Also guard the handler itself, not just the disabled button.
        if not is_session_active() or load_error is not None:
            return

        # Normalize both typed and selected names into the standard spelling.
        # Unsupported text has no known unit, so explain how to correct it.
        name = canonical_activity(activity_name.value)
        raw_value = (activity_value.value or "").strip()
        activity_name_error.value = "" if name else "Choose or type one of the suggested activities."
        activity_name_error.visible = name is None
        activity_value.error_text = None
        # Refresh here too in case the user typed a name and immediately saved.
        update_value_label()

        try:
            # float() accepts whole numbers and decimals, such as 5 and 2.5.
            # It raises ValueError for input such as an empty string or "hello".
            value = float(raw_value)
            # float() also accepts "nan" and "inf", so check those explicitly.
            # For this simple activity form, zero and negative values are invalid.
            if not isfinite(value) or value <= 0:
                # Send these invalid numbers to the same error handler below.
                raise ValueError
            # Fractional km, minutes, and cups are useful (e.g. 1.5 cups), but a
            # step count must be whole. 1000.0 is fine; 1000.5 is not.
            if name == "Steps" and not value.is_integer():
                activity_value.error_text = "Enter a whole number of steps."
        except ValueError:
            activity_value.error_text = "Enter a number greater than zero."

        if activity_name_error.visible or activity_value.error_text:
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
            "member_id": member_id,
            # Store the unit NOW rather than deriving it when reading history.
            # If measurement choices change later, this entry keeps its meaning.
            "unit": ACTIVITY_UNITS[name],
        }
        # Save a candidate list BEFORE changing memory or the interface. If disk
        # writing fails, the old history and the user's form input stay intact.
        try:
            save_habits(habits + [habit])
        except StorageError as error:
            storage_status.value = f"{error}\nYour entry was not saved. Please try again."
            storage_status.color = "#FCA5A5"
            storage_status.visible = True
            # Show the failed write in diagnostics as well as beside the form.
            local_storage_health.value = f"Last save failed: {error}"
            local_storage_health.color = "#FCA5A5"
            page.update()
            return

        # Disk saving succeeded, so it is now safe to update the in-memory list.
        habits.append(habit)
        # Insert the card at index 0 (the start) so the newest entry appears first.
        # habits keeps save order; activity_list keeps the visual newest-first order.
        activity_list.controls.insert(0, make_activity_card(habit))
        # Replace the placeholder with the list after a successful save.
        empty_state.visible = False
        activity_list.visible = True
        # Clear the form for the next entry. Validation errors are already None.
        activity_name.value = ""
        activity_value.value = ""
        update_value_label()
        storage_status.value = "Activity saved to this device."
        storage_status.color = "#66FCF1"
        storage_status.visible = True
        local_storage_health.value = "Last activity saved successfully to this device."
        local_storage_health.color = "#66FCF1"
        refresh_summaries()
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
                ft.Text(
                    f"Logging as {current_member['name']}",
                    size=12,
                    color="#8D8D8D",
                ),
                ft.Column(
                    controls=[
                        ft.Text("Activity (type to see suggestions)", color="white", size=12),
                        activity_name,
                        activity_name_error,
                    ],
                    spacing=6,
                    tight=True,
                ),
                activity_value,
                storage_status,
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
                    disabled=load_error is not None,
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

    def make_tab_panel(content):
        # Give all three pages the same border, background, and padding without
        # repeating those settings. Each call creates a NEW Container instance.
        return ft.Container(
            bgcolor="#1F2833",
            padding=20,
            border_radius=16,
            border=ft.Border.all(1, "#45A29E"),
            content=content,
        )

    timeline_view = make_tab_panel(
        ft.Column(
            controls=[
                ft.Text("Family Timeline", size=20, weight="bold", color="white"),
                ft.Text(
                    "All local family activities, including historical demo entries. "
                    "Entries without an owner remain Unassigned.",
                    color="#8D8D8D",
                ),
                # A failed load must not look like an empty history. The form
                # shows the full error and recovery instructions; this explains
                # why the timeline itself has no entries in that situation.
                ft.Text(
                    "History could not be loaded. Check the warning beside the form.",
                    color="#FCA5A5",
                    visible=load_error is not None,
                ),
                empty_state,
                activity_list,
            ],
            expand=True,
            spacing=12,
        )
    )

    personal_view = make_tab_panel(
        ft.Column(
            controls=[
                ft.Text("Personal Profile", size=20, weight="bold", color="white"),
                ft.Row(controls=[personal_avatar, personal_name], spacing=12),
                ft.Text(f"Signed in as {current_member['email']}", color="#66FCF1"),
                ft.Text(
                    "Your activity history and daily progress. To use a different "
                    "account, log out and log in again.",
                    color="white",
                ),
                ft.Divider(color="#45A29E"),
                personal_summary,
                daily_progress_panel,
                personal_empty,
                personal_list,
            ],
            # Scroll the whole Personal page so progress and history remain
            # reachable even in a short window. Children do not expand vertically.
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
        )
    )

    cloud_view = make_tab_panel(
        ft.Column(
            controls=[
                ft.Text("Cloud Status", size=20, weight="bold", color="white"),
                ft.Text("Airtable: not connected", color="#FBBF24", weight="bold"),
                ft.Text(
                    "Cloud syncing is not implemented yet. Activities are saved "
                    "only on this computer, not shared with other devices.",
                    color="white",
                ),
                ft.Divider(color="#45A29E"),
                ft.Text("Local storage diagnostics", weight="bold", color="white"),
                local_storage_health,
                cloud_summary,
                ft.Text(f"Storage file: {DATA_FILE}", size=12, color="#8D8D8D"),
                # Show the real load error here too, so diagnostics is useful
                # even while the timeline cannot display the damaged history.
                ft.Text(load_error or "", color="#FCA5A5", visible=load_error is not None),
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
        )
    )

    # Tabs is the shared controller: it connects a TabBar (clickable labels) to a
    # TabBarView (page contents). Both MUST be inside this SAME Tabs control.
    # Previously the tab bar existed alone, with one unrelated panel below it,
    # so choosing a label could not change the contents of that panel.
    def change_tab(e):
        # Recalculate the local date when navigating too. For example, returning
        # to Personal after midnight should not keep displaying yesterday's total.
        # We also refresh after saves; no timer is needed here.
        if not is_session_active():
            return
        refresh_summaries()
        page.update()

    data_panel = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        length=3,
        on_change=change_tab,
        expand=True,
        content=ft.Column(
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label="Family Timeline", icon=ft.Icons.DASHBOARD_OUTLINED),
                        ft.Tab(label="Personal", icon=ft.Icons.PERSON_OUTLINED),
                        ft.Tab(label="Cloud Status", icon=ft.Icons.CLOUD_SYNC_OUTLINED),
                    ],
                ),
                # Page order matches label order exactly: index 0 is Timeline,
                # index 1 is Personal, and index 2 is Cloud Status. Flet handles
                # selection and animation; no custom click handler is needed.
                ft.TabBarView(
                    controls=[timeline_view, personal_view, cloud_view],
                    expand=True,
                ),
            ],
            expand=True,
            spacing=12,
        ),
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

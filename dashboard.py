"""Desktop dashboard with Airtable as the only activity database."""

import asyncio
from datetime import datetime
from math import isfinite
from uuid import uuid4

import flet as ft

from activities import ACTIVITY_UNITS, DEMO_STEP_GOAL, DEMO_WATER_GOAL, canonical_activity, daily_totals
from airtable_api import AirtableError, check_connection, get_destination, upload_batch, download_records
from cloud_history import parse_cloud_history, newest_first


DEMO_MEMBERS = {
    "demo-alex": {"name": "Alex Morgan", "color": "#2563EB"},
    "demo-jamie": {"name": "Jamie Morgan", "color": "#7C3AED"},
    "demo-sam": {"name": "Sam Morgan", "color": "#047857"},
}


def member_details(member_id, members, saved_name=None):
    """Use account details first, then a recorded name for historical entries."""
    member = members.get(member_id) or DEMO_MEMBERS.get(member_id)
    if member is None:
        name = saved_name if member_id and saved_name else "Unknown member" if member_id else "Unassigned"
        colors = ("#2563EB", "#7C3AED", "#047857")
        color = colors[sum(ord(c) for c in member_id) % len(colors)] if member_id else "#4B5563"
        member = {"name": name, "color": color}
    initials = "".join(word[0] for word in member["name"].split()[:2]).upper()
    return {**member, "initials": initials}


def build_dashboard(page, current_member, members, is_session_active, on_logout):
    """Build views for one signed-in session; never read or write a JSON file."""
    if not is_session_active():
        return
    member_id = current_member["id"]
    # This list is only a temporary view of Airtable, not a local database.
    # Closing the app discards it. Login schedules a fresh cloud download.
    habits = []
    history_loaded = False
    busy = False
    # Keep a failed save's ID in memory so retrying updates the SAME cloud row,
    # even if Airtable saved it but its response was lost on the network.
    draft_id = None
    draft_time = None

    activity_name = ft.AutoComplete(
        suggestions=[ft.AutoCompleteSuggestion(key=name, value=name) for name in ACTIVITY_UNITS],
        suggestions_max_height=200, data="activity_name",
    )
    name_error = ft.Text(color="#FCA5A5", size=12, visible=False, data="activity_name_error")
    activity_value = ft.TextField(
        label="Value (choose an activity first)", color="white", border_color="#45A29E",
        keyboard_type=ft.KeyboardType.NUMBER, data="activity_value",
    )
    save_status = ft.Text("", color="#66FCF1", data="save_status")
    save_spinner = ft.ProgressRing(width=24, height=24, visible=False, data="save_spinner")
    timeline_message = ft.Text("Loading history from Airtable...", color="#8D8D8D", data="timeline_message")
    timeline_list = ft.ListView(expand=True, spacing=12, data="timeline_list")
    personal_name = ft.Text(current_member["name"], size=18, weight="bold", color="white")
    profile = member_details(member_id, members)
    personal_avatar = ft.CircleAvatar(content=ft.Text(profile["initials"]), bgcolor=profile["color"], color="white")
    personal_summary = ft.Text("History has not loaded yet.", color="#66FCF1", data="personal_summary")
    personal_list = ft.Column(tight=True, spacing=12, data="personal_list")
    personal_empty = ft.Text("", color="#8D8D8D")
    progress_date = ft.Text(weight="bold", color="white", data="progress_date")
    steps_label = ft.Text(color="white", data="steps_label")
    water_label = ft.Text(color="white", data="water_label")
    steps_bar = ft.ProgressBar(value=0, color="#66FCF1", bgcolor="#0B0C10", data="steps_bar")
    water_bar = ft.ProgressBar(value=0, color="#60A5FA", bgcolor="#0B0C10", data="water_bar")
    progress_panel = ft.Column(
        controls=[progress_date, steps_label, steps_bar, water_label, water_bar,
                  ft.Text(f"Demo goals: {DEMO_STEP_GOAL:,} steps and {DEMO_WATER_GOAL} cups. Not medical advice.",
                          size=12, color="#8D8D8D")],
        spacing=8, tight=True, visible=False, data="progress_panel",
    )
    cloud_status = ft.Text("History has not loaded yet.", color="#FBBF24", data="cloud_history_status")
    cloud_summary = ft.Text("Cloud activity count unavailable.", color="white", data="cloud_history_summary")
    cloud_spinner = ft.ProgressRing(width=24, height=24, visible=False, data="cloud_history_spinner")
    connection_status = ft.Text("Connection not tested separately.", color="#8D8D8D", data="airtable_status")
    connection_spinner = ft.ProgressRing(width=24, height=24, visible=False, data="airtable_spinner")

    def update_value_label():
        name = canonical_activity(activity_name.value)
        unit = ACTIVITY_UNITS.get(name)
        activity_value.label = f"Value ({unit})" if unit else "Value (choose an activity first)"
        activity_value.helper_text = (
            "Add additional steps, not your cumulative daily total." if name == "Steps" else
            "Add the cups you just drank." if name == "Water Intake" else None
        )

    def change_activity(e):
        if not is_session_active():
            return
        name_error.visible = False
        activity_value.error_text = None
        update_value_label()
        page.update()

    def select_activity(e):
        activity_name.value = e.selection.value
        change_activity(e)

    activity_name.on_change = change_activity
    activity_name.on_select = select_activity

    def make_card(habit):
        member = member_details(habit.get("member_id"), members, habit.get("member_name"))
        return ft.Container(
            bgcolor="#0B0C10", padding=16, border_radius=10,
            content=ft.Row(
                controls=[
                    ft.CircleAvatar(content=ft.Text(member["initials"]), bgcolor=member["color"], color="white"),
                    ft.Column(controls=[
                        ft.Text(member["name"], size=12, color="#8D8D8D"),
                        ft.Text(habit["name"], weight="bold", color="white"),
                        ft.Text(f"Value: {habit['value']:g} {habit.get('unit', '(unit unspecified)')}", color="#66FCF1"),
                        ft.Text(habit["logged_at"].strftime("%d %b %Y, %H:%M"), size=12, color="#8D8D8D"),
                    ], spacing=4, expand=True),
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )

    def refresh_views():
        # A failed first download means "unknown", not zero progress. After a
        # later network error the previous successful in-memory view is retained.
        progress_panel.visible = history_loaded
        if not history_loaded:
            return
        timeline_list.controls = [make_card(h) for h in newest_first(habits)]
        timeline_message.value = "No activities in Airtable yet."
        timeline_message.visible = not habits
        mine = [h for h in habits if h.get("member_id") == member_id]
        personal_list.controls = [make_card(h) for h in newest_first(mine)]
        personal_summary.value = f"Activities for {current_member['name']}: {len(mine)}"
        personal_empty.value = "No activities for you yet." if not mine else ""
        cloud_summary.value = f"Cloud activities loaded: {len(habits)}"
        today = datetime.now().date()
        totals = daily_totals(habits, member_id, today)
        progress_date.value = f"Today's progress — {today.strftime('%d %b %Y')}"
        step_ratio = totals["steps"] / DEMO_STEP_GOAL
        water_ratio = totals["cups"] / DEMO_WATER_GOAL
        steps_label.value = f"Steps: {totals['steps']:,} / {DEMO_STEP_GOAL:,} ({step_ratio * 100:g}%)"
        water_label.value = f"Water: {totals['cups']:g} / {DEMO_WATER_GOAL} cups ({water_ratio * 100:g}%)"
        steps_bar.value, water_bar.value = min(step_ratio, 1), min(water_ratio, 1)

    def set_busy(value, saving=False):
        # Only one history operation runs at a time. Otherwise an old download
        # could replace a new save's view, or a double-click could submit twice.
        nonlocal busy
        busy = value
        save_button.disabled = value or not history_loaded
        refresh_button.disabled = value
        save_spinner.visible = value and saving
        cloud_spinner.visible = value and not saving
        page.update()

    async def refresh_from_airtable(e=None):
        nonlocal history_loaded
        if not is_session_active() or busy:
            return
        set_busy(True)
        cloud_status.value = "Loading history from Airtable..."
        cloud_status.color = "#FBBF24"
        page.update()
        try:
            destination = get_destination()
            records = await asyncio.to_thread(download_records, destination)
            if not is_session_active():
                return
            parsed = parse_cloud_history(records)
            # Airtable is the source of truth. A successful refresh replaces
            # ONLY the temporary view, reflecting cloud edits/deletions too.
            # Invalid/empty rows are counted and skipped, never made into logs.
            habits[:] = parsed["habits"]
            history_loaded = True
            refresh_views()
            cloud_status.value = (
                f"Loaded {len(habits)} activities. Skipped {parsed['empty']} empty, "
                f"{parsed['invalid']} invalid, {parsed['duplicates']} duplicate-ID rows. "
                f"Last refresh: {datetime.now().strftime('%d %b %Y, %H:%M:%S')}."
            )
            cloud_status.color = "#66FCF1"
        except AirtableError as error:
            if is_session_active():
                cloud_status.value = f"Refresh failed: {error}"
                cloud_status.color = "#FCA5A5"
                if not history_loaded:
                    timeline_message.value = "History unavailable. Check Cloud Status and try Refresh."
        except Exception:
            if is_session_active():
                cloud_status.value = "Could not load history. Please try Refresh again."
                cloud_status.color = "#FCA5A5"
        finally:
            if is_session_active():
                set_busy(False)

    async def save_log(e):
        nonlocal draft_id, draft_time
        if not is_session_active() or busy or not history_loaded:
            return
        name = canonical_activity(activity_name.value)
        name_error.value = "Choose or type a suggested activity." if name is None else ""
        name_error.visible = name is None
        activity_value.error_text = None
        try:
            value = float((activity_value.value or "").strip())
            if not isfinite(value) or value <= 0:
                raise ValueError
            if name == "Steps" and not value.is_integer():
                activity_value.error_text = "Enter a whole number of steps."
        except ValueError:
            activity_value.error_text = "Enter a number greater than zero."
        update_value_label()
        if name_error.visible or activity_value.error_text:
            page.update()
            return
        if draft_id is None:
            draft_id, draft_time = uuid4().hex, datetime.now().astimezone()
        habit = {
            "log_id": draft_id, "name": name, "value": value, "unit": ACTIVITY_UNITS[name],
            "member_id": member_id, "member_name": current_member["name"], "logged_at": draft_time,
        }
        set_busy(True, saving=True)
        save_status.value = "Saving to Airtable..."
        save_status.color = "#FBBF24"
        page.update()
        try:
            destination = get_destination()
            # There is no local save or offline queue. Only show success after
            # Airtable confirms this LogID. Upsert makes an in-session retry safe.
            await asyncio.to_thread(upload_batch, [habit], {member_id: current_member["name"]}, destination)
            if not is_session_active():
                return
            habits[:] = [h for h in habits if h["log_id"] != habit["log_id"]] + [habit]
            activity_name.value = activity_value.value = ""
            draft_id = draft_time = None
            update_value_label()
            refresh_views()
            save_status.value = "Saved to Airtable."
            save_status.color = "#66FCF1"
        except AirtableError as error:
            if is_session_active():
                save_status.value = f"Save not confirmed: {error} Keep the app open to retry, or refresh to check the cloud."
                save_status.color = "#FCA5A5"
        except Exception:
            if is_session_active():
                save_status.value = "Save was not confirmed. Keep the app open to retry, or refresh to check the cloud."
                save_status.color = "#FCA5A5"
        finally:
            if is_session_active():
                set_busy(False)

    async def test_connection(e):
        if not is_session_active() or connection_button.disabled:
            return
        connection_button.disabled = True
        connection_spinner.visible = True
        connection_status.value = "Checking Airtable..."
        page.update()
        try:
            message = await asyncio.to_thread(check_connection)
        except AirtableError as error:
            message = str(error)
        except Exception:
            message = "Could not check the connection. Please try again."
        finally:
            connection_button.disabled = False
            connection_spinner.visible = False
        if is_session_active():
            connection_status.value = message
            page.update()

    save_button = ft.Button(
        "Save Log", icon=ft.Icons.SAVE_OUTLINED, on_click=save_log, disabled=True,
        bgcolor="#66FCF1", color="#0B0C10", width=float("inf"), height=46,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), data="save_log",
    )
    refresh_button = ft.Button(
        "Refresh from Airtable", icon=ft.Icons.CLOUD_DOWNLOAD_OUTLINED,
        on_click=refresh_from_airtable, data="refresh_airtable_history",
    )
    connection_button = ft.Button("Test Connection", on_click=test_connection, data="test_airtable_connection")

    def panel(content):
        return ft.Container(bgcolor="#1F2833", padding=20, border_radius=16,
                            border=ft.Border.all(1, "#45A29E"), content=content)

    form = panel(ft.Column(controls=[
        ft.Text("Log New Activity", size=16, weight="bold", color="white"),
        ft.Text(f"Logging as {current_member['name']}", color="#8D8D8D"),
        ft.Text("Activity (type for suggestions)", size=12, color="white"),
        activity_name, name_error, activity_value, save_status, save_button, save_spinner,
        ft.Text("Internet required. Unsaved input is lost when this app closes.", size=12, color="#8D8D8D"),
    ], tight=True, spacing=12))
    form.width = 340
    timeline = panel(ft.Column(controls=[
        ft.Text("Family Timeline", size=20, weight="bold", color="white"),
        timeline_message, timeline_list,
    ], expand=True, spacing=12))
    personal = panel(ft.Column(controls=[
        ft.Text("Personal Profile", size=20, weight="bold", color="white"),
        ft.Row(controls=[personal_avatar, personal_name]),
        ft.Text(f"Signed in as {current_member['email']}", color="#66FCF1"),
        personal_summary, progress_panel, personal_empty, personal_list,
    ], scroll=ft.ScrollMode.AUTO, spacing=12))
    cloud = panel(ft.Column(controls=[
        ft.Text("Cloud Status", size=20, weight="bold", color="white"),
        ft.Text("Accounts and activities are in Airtable. No local JSON database or offline queue.", color="white"),
        ft.Row(controls=[refresh_button, cloud_spinner]), cloud_status, cloud_summary,
        ft.Divider(color="#45A29E"),
        ft.Row(controls=[connection_button, connection_spinner]), connection_status,
        ft.Text("Test Connection checks read access; saving requires write access too.", size=12, color="#8D8D8D"),
    ], scroll=ft.ScrollMode.AUTO, spacing=12))

    def change_tab(e):
        if is_session_active():
            refresh_views()  # Recalculate today's date without extra network calls.
            page.update()

    tabs = ft.Tabs(
        length=3, selected_index=0, expand=True, on_change=change_tab,
        content=ft.Column(controls=[
            ft.TabBar(tabs=[ft.Tab(label="Family Timeline"), ft.Tab(label="Personal"), ft.Tab(label="Cloud Status")]),
            ft.TabBarView(controls=[timeline, personal, cloud], expand=True),
        ], expand=True, spacing=12), data="dashboard_tabs",
    )
    page.add(
        panel(ft.Row(controls=[ft.Icon(ft.Icons.FITNESS_CENTER, color="#66FCF1"),
                              ft.Text("VitalityHub", size=22, weight="bold", color="white"),
                              ft.Container(expand=True), ft.Button("Log Out", on_click=on_logout, data="logout")])),
        ft.Row(controls=[form, tabs], expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
    )
    # Start loading immediately after login, not from a local file. Flet runs
    # this async function without freezing the window during the HTTP request.
    page.run_task(refresh_from_airtable)

import flet as ft

def main(page: ft.Page):
    page.title = "VitalityHub | Premium Capstone"
    page.bgcolor = "#0B0C10" 
    page.padding = 24
    habits = []

    def make_header():
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

    exercise_options = ["Running", "Swimming", "Cycling", "Yoga", "Water Intake", "Gym"]
    
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
                ft.TextField(label="Activity Name", color="white", border_color="#45A29E"),
                ft.TextField(
                    label="Value (Distance / Cups / Mins)", 
                    color="white", 
                    border_color="#45A29E",
                    keyboard_type=ft.KeyboardType.NUMBER
                ),
                ft.Button("Save Log", bgcolor="#66FCF1", color="#0B0C10", expand=True)
            ],
            spacing=12,
        ),
    )

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
                    controls=[
                        ft.Icon(ft.Icons.DIRECTIONS_RUN, size=48, color="#66FCF1"),
                        ft.Text("No activities logged today.", color="#8D8D8D"),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ),
        ],
        expand=True,
        spacing=12,
    )

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

ft.run(main)

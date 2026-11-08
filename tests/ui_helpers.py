"""Small test substitutes for Flet's page and its control lookup."""

import flet as ft


class TestPage:
    def __init__(self):
        self.controls = []
        self.tasks = []
        self.updates = 0

    def add(self, *controls):
        self.controls.extend(controls)

    def clean(self):
        self.controls.clear()

    def update(self):
        self.updates += 1

    def run_task(self, handler):
        # Tests explicitly run scheduled coroutines with mocked cloud APIs.
        self.tasks.append(handler)


def walk(control):
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)
    for child in getattr(control, "controls", []):
        yield from walk(child)


def find(page, label):
    return next(c for root in page.controls for c in walk(root) if getattr(c, "data", None) == label)

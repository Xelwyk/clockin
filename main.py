# /// script
# dependencies = [
#     "textual>=0.80.0",
# ]
# ///
"""ClockIn - Interactive TUI for tracking work hours and calculated end time.

Formula:
    End Time = (Start Time + 8h) - Overtime
"""

from __future__ import annotations

import re
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Digits, Footer, Header, Input, Label


def parse_time_str(val: str) -> tuple[int, int] | None:
    """Parse time string like '08:30', '8:30', '830', or '8' into (hours, minutes)."""
    val = val.strip()
    if not val:
        return None

    # Format HH:MM or H:MM
    match = re.match(r"^(\d{1,2}):(\d{1,2})$", val)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
        return None

    # Format HHMM or HMM (e.g. 0830 or 830)
    match = re.match(r"^(\d{1,2})(\d{2})$", val)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
        return None

    # Single number like "8" or "14" -> 08:00 or 14:00
    match = re.match(r"^(\d{1,2})$", val)
    if match:
        h = int(match.group(1))
        if 0 <= h < 24:
            return h, 0
        return None

    return None


def parse_overtime_str(val: str) -> int | None:
    """Parse overtime string like '+00:30', '-01:15', '00:45', '-45', '+15m', '-1h' into signed total minutes."""
    val = val.strip()
    if not val:
        return None

    sign = -1 if val.startswith("-") else 1
    clean = val.lstrip("+-").strip()

    # Formats like 1h, 1.5h, 30m, 45min
    match_dur = re.match(r"^(\d+(?:\.\d+)?)\s*(h|hr|hrs|m|min|mins)$", clean, re.IGNORECASE)
    if match_dur:
        amount, unit = float(match_dur.group(1)), match_dur.group(2).lower()
        if unit.startswith("h"):
            return int(round(sign * amount * 60))
        return int(round(sign * amount))

    # Format HH:MM or H:MM
    match_colon = re.match(r"^(\d{1,2}):(\d{1,2})$", clean)
    if match_colon:
        h, m = int(match_colon.group(1)), int(match_colon.group(2))
        if 0 <= m < 60:
            return sign * (h * 60 + m)
        return None

    # Format HHMM (e.g. 0130 -> 1h 30m)
    match_4digit = re.match(r"^(\d{2})(\d{2})$", clean)
    if match_4digit:
        h, m = int(match_4digit.group(1)), int(match_4digit.group(2))
        if 0 <= m < 60:
            return sign * (h * 60 + m)
        return None

    # Plain integer minutes (e.g. 30 -> 30 mins)
    match_num = re.match(r"^(\d+)$", clean)
    if match_num:
        mins = int(match_num.group(1))
        return sign * mins

    return None


def format_time(hours: int, minutes: int) -> str:
    """Format hours and minutes as HH:MM."""
    return f"{hours:02d}:{minutes:02d}"


def format_overtime(total_minutes: int) -> str:
    """Format signed minutes as +HH:MM or -HH:MM."""
    sign = "-" if total_minutes < 0 else "+"
    total = abs(total_minutes)
    h = total // 60
    m = total % 60
    return f"{sign}{h:02d}:{m:02d}"


def calculate_end_time(start_mins: int, overtime_mins: int) -> tuple[int, int, int]:
    """Calculate End Time = (start_mins + 8h) - overtime_mins.

    Returns (end_hours, end_minutes, day_offset).
    """
    total_target = start_mins + (8 * 60) - overtime_mins
    day_offset = total_target // 1440
    norm_mins = total_target % 1440
    return norm_mins // 60, norm_mins % 60, day_offset


class ClockInApp(App):
    """Textual TUI for ClockIn hours calculator."""

    TITLE = "CLOCKIN"
    SUB_TITLE = "Work Hours & Departure Calculator"

    CSS = """
    Screen {
        background: $surface;
        align: center middle;
    }

    #main-container {
        width: 100%;
        max-width: 120;
        height: auto;
        padding: 1;
    }

    #cards-container {
        height: auto;
        layout: horizontal;
        margin-bottom: 1;
    }

    .clock-card {
        width: 1fr;
        background: $panel;
        padding: 1;
        border: heavy $border;
        height: auto;
        margin: 0 1;
    }

    #card-start {
        border: heavy $accent;
    }

    #card-overtime {
        border: heavy $warning;
    }

    #card-end {
        border: heavy $success;
    }

    .card-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        padding-bottom: 0;
    }

    #title-start {
        color: $accent;
    }

    #title-overtime {
        color: $warning;
    }

    #title-end {
        color: $success;
    }

    .clock-display {
        text-align: center;
        width: 100%;
        height: 3;
        margin: 1 0;
        content-align: center middle;
    }

    .time-input {
        margin: 0 0 1 0;
        width: 100%;
        text-align: center;
    }

    .input-hint {
        color: $text-muted;
        text-align: center;
        text-style: italic;
        margin-bottom: 1;
        height: 1;
    }

    .btn-row {
        height: auto;
        align: center middle;
        margin: 0 0 1 0;
    }

    .btn-row Button {
        width: 1fr;
        min-width: 5;
        height: 3;
        margin: 0 1;
    }

    #end-status-box {
        background: $surface;
        border: round $success;
        padding: 1;
        margin-top: 1;
        text-align: center;
        height: auto;
    }

    #end-day-tag {
        text-align: center;
        text-style: bold;
        color: $success-lighten-2;
    }

    #end-detail-label {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("n", "snap_now", "Start = Now", show=True),
        Binding("r", "reset_overtime", "Reset Overtime", show=True),
        Binding("d", "toggle_dark", "Toggle Theme", show=True),
    ]

    # Reactive variables storing minutes
    start_minutes = reactive(540)  # Default 09:00 AM (9 * 60)
    overtime_minutes = reactive(0)    # Default 00:00

    def __init__(self) -> None:
        super().__init__()
        # Initialize start time to current time or default 09:00
        now = datetime.now()
        self.start_minutes = now.hour * 60 + now.minute

    def compose(self) -> ComposeResult:
        """Compose the layout with three cards and the formula summary."""
        yield Header(show_clock=True)

        with Vertical(id="main-container"):
            with Container(id="cards-container"):
                # Card 1: Start Time
                with Vertical(classes="clock-card", id="card-start"):
                    yield Label("[1] START TIME", classes="card-title", id="title-start")
                    yield Digits("09:00", id="digits-start", classes="clock-display")
                    yield Input(
                        value=format_time(self.start_minutes // 60, self.start_minutes % 60),
                        placeholder="HH:MM",
                        id="input-start",
                        classes="time-input",
                    )
                    yield Label("Type time or use quick buttons", classes="input-hint")
                    with Horizontal(classes="btn-row"):
                        yield Button("-1h", id="btn-start-m60")
                        yield Button("+1h", id="btn-start-p60")
                        yield Button("-15m", id="btn-start-m15")
                        yield Button("+15m", id="btn-start-p15")
                    with Horizontal(classes="btn-row btn-primary-row"):
                        yield Button("-1m", id="btn-start-m1")
                        yield Button("+1m", id="btn-start-p1")
                        yield Button("Now", id="btn-start-now", variant="primary")

                # Card 2: Overtime
                with Vertical(classes="clock-card", id="card-overtime"):
                    yield Label("[2] OVERTIME", classes="card-title", id="title-overtime")
                    yield Digits("+00:00", id="digits-overtime", classes="clock-display")
                    yield Input(
                        value="+00:00",
                        placeholder="±HH:MM (e.g. -00:30)",
                        id="input-overtime",
                        classes="time-input",
                    )
                    yield Label("Supports negative values", classes="input-hint")
                    with Horizontal(classes="btn-row"):
                        yield Button("-1h", id="btn-overtime-m60")
                        yield Button("+1h", id="btn-overtime-p60")
                        yield Button("-15m", id="btn-overtime-m15")
                        yield Button("+15m", id="btn-overtime-p15")
                    with Horizontal(classes="btn-row btn-primary-row"):
                        yield Button("-5m", id="btn-overtime-m5")
                        yield Button("+5m", id="btn-overtime-p5")
                        yield Button("+/-", id="btn-overtime-toggle", variant="warning")
                        yield Button("0:00", id="btn-overtime-zero", variant="error")

                # Card 3: End Time (Calculated)
                with Vertical(classes="clock-card", id="card-end"):
                    yield Label("[3] END TIME (Calculated)", classes="card-title", id="title-end")
                    yield Digits("17:00", id="digits-end", classes="clock-display")
                    with Vertical(id="end-status-box"):
                        yield Label("Same day", id="end-day-tag")
                        yield Label("Standard 8h Shift", id="end-detail-label")


        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted; sync UI with initial state."""
        self.update_all_views()

    def set_start(self, hours: int, minutes: int) -> None:
        """Set start time directly."""
        self.start_minutes = (hours % 24) * 60 + (minutes % 60)

    def set_overtime(self, minutes: int) -> None:
        """Set overtime directly."""
        self.overtime_minutes = minutes

    def calculate_end(self) -> tuple[int, int, int]:
        """Return (end_hours, end_minutes, day_offset)."""
        return calculate_end_time(self.start_minutes, self.overtime_minutes)

    def watch_start_minutes(self, old_val: int, new_val: int) -> None:
        """Reactive watcher when start time changes."""
        self.update_all_views()

    def watch_overtime_minutes(self, old_val: int, new_val: int) -> None:
        """Reactive watcher when overtime changes."""
        self.update_all_views()

    def update_all_views(self) -> None:
        """Refresh all clock displays, input values, and formula preview."""
        # Update Start Time widgets
        st_h = (self.start_minutes % 1440) // 60
        st_m = (self.start_minutes % 1440) % 60
        st_str = format_time(st_h, st_m)

        try:
            digits_start = self.query_one("#digits-start", Digits)
            digits_start.update(st_str)
        except Exception:
            pass

        try:
            input_start = self.query_one("#input-start", Input)
            if not input_start.has_focus:
                input_start.value = st_str
        except Exception:
            pass

        # Update Overtime widgets
        overtime_str = format_overtime(self.overtime_minutes)
        try:
            digits_overtime = self.query_one("#digits-overtime", Digits)
            digits_overtime.update(overtime_str)
        except Exception:
            pass

        try:
            input_overtime = self.query_one("#input-overtime", Input)
            if not input_overtime.has_focus:
                input_overtime.value = overtime_str
        except Exception:
            pass

        # Update End Time widgets
        end_h, end_m, day_offset = self.calculate_end()
        end_str = format_time(end_h, end_m)

        try:
            digits_end = self.query_one("#digits-end", Digits)
            digits_end.update(end_str)
        except Exception:
            pass

        try:
            tag = self.query_one("#end-day-tag", Label)
            if day_offset == 0:
                tag.update("[bold green]Same Day[/bold green]")
            elif day_offset > 0:
                tag.update(f"[bold yellow]+{day_offset} Day (Next Day)[/bold yellow]")
            else:
                tag.update(f"[bold magenta]{day_offset} Day (Previous Day)[/bold magenta]")
        except Exception:
            pass

        # Base 8h end time (start + 8h)
        base_target = self.start_minutes + (8 * 60)
        base_h = (base_target % 1440) // 60
        base_m = (base_target % 1440) % 60
        base_str = format_time(base_h, base_m)

        try:
            detail = self.query_one("#end-detail-label", Label)
            detail.update(f"Base 8h finish: {base_str} | Overtime adjust: {-self.overtime_minutes:+d}m")
        except Exception:
            pass



    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle user typing in the Start or Overtime input boxes."""
        if event.input.id == "input-start":
            parsed = parse_time_str(event.value)
            if parsed is not None:
                h, m = parsed
                new_start = h * 60 + m
                if new_start != self.start_minutes:
                    self.start_minutes = new_start

        elif event.input.id == "input-overtime":
            parsed = parse_overtime_str(event.value)
            if parsed is not None:
                if parsed != self.overtime_minutes:
                    self.overtime_minutes = parsed

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks for quick adjustments."""
        btn_id = event.button.id
        if not btn_id:
            return

        # Start Time adjustments
        if btn_id == "btn-start-m60":
            self.start_minutes = (self.start_minutes - 60) % 1440
        elif btn_id == "btn-start-p60":
            self.start_minutes = (self.start_minutes + 60) % 1440
        elif btn_id == "btn-start-m15":
            self.start_minutes = (self.start_minutes - 15) % 1440
        elif btn_id == "btn-start-p15":
            self.start_minutes = (self.start_minutes + 15) % 1440
        elif btn_id == "btn-start-m1":
            self.start_minutes = (self.start_minutes - 1) % 1440
        elif btn_id == "btn-start-p1":
            self.start_minutes = (self.start_minutes + 1) % 1440
        elif btn_id == "btn-start-now":
            self.action_snap_now()

        # Overtime adjustments
        elif btn_id == "btn-overtime-m60":
            self.overtime_minutes -= 60
        elif btn_id == "btn-overtime-p60":
            self.overtime_minutes += 60
        elif btn_id == "btn-overtime-m15":
            self.overtime_minutes -= 15
        elif btn_id == "btn-overtime-p15":
            self.overtime_minutes += 15
        elif btn_id == "btn-overtime-m5":
            self.overtime_minutes -= 5
        elif btn_id == "btn-overtime-p5":
            self.overtime_minutes += 5
        elif btn_id == "btn-overtime-toggle":
            self.overtime_minutes = -self.overtime_minutes
        elif btn_id == "btn-overtime-zero":
            self.action_reset_overtime()

    def action_snap_now(self) -> None:
        """Snap start time to current system time."""
        now = datetime.now()
        self.start_minutes = now.hour * 60 + now.minute
        self.notify(f"Start time set to Now: {format_time(now.hour, now.minute)}")

    def action_reset_overtime(self) -> None:
        """Reset overtime to 00:00."""
        self.overtime_minutes = 0
        self.notify("Overtime reset to +00:00")


def main() -> None:
    """Run the ClockIn application."""
    app = ClockInApp()
    app.run()


if __name__ == "__main__":
    main()

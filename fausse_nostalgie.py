import calendar
import time
import sys
import pyfiglet
import termios
import tty
import select
import signal
import shutil
import atexit
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# CONFIGURATION
# ============================================================

BASE_WIDTH = 76
term_width = BASE_WIDTH
term_height = 24

# ============================================================
# MODES
# ============================================================

MODE_CLOCK = "clock"
MODE_CALENDAR = "calendar"
current_mode = MODE_CLOCK

# ============================================================
# TIME FORMAT
# ============================================================

USE_24H = True  # toggled with "t"

# ============================================================
# TIMEZONE CONFIGURATION
# ============================================================

# Timezones arranged by GMT offset for smooth progression
# 1-9 keys map to indices 0-8
TIMEZONES = [
    {"name": "LA", "tz": ZoneInfo("America/Los_Angeles"), "gmt": "GMT-8"},      # 1: GMT-8
    {"name": "NY", "tz": ZoneInfo("America/New_York"), "gmt": "GMT-5"},        # 2: GMT-5
    {"name": "SAO PAULO", "tz": ZoneInfo("America/Sao_Paulo"), "gmt": "GMT-3"}, # 3: GMT-3
    {"name": "LONDON", "tz": ZoneInfo("Europe/London"), "gmt": "GMT+0"},       # 4: GMT+0
    {"name": "PARIS", "tz": ZoneInfo("Europe/Paris"), "gmt": "GMT+1"},         # 5: GMT+1
    {"name": "CAIRO", "tz": ZoneInfo("Africa/Cairo"), "gmt": "GMT+2"},         # 6: GMT+2
    {"name": "DUBAI", "tz": ZoneInfo("Asia/Dubai"), "gmt": "GMT+4"},           # 7: GMT+4
    {"name": "TOKYO", "tz": ZoneInfo("Asia/Tokyo"), "gmt": "GMT+9"},           # 8: GMT+9
    {"name": "SYDNEY", "tz": ZoneInfo("Australia/Sydney"), "gmt": "GMT+11"},   # 9: GMT+11
]

# Track which timezones are active (indices into TIMEZONES)
active_timezones = []  # Start with no extra timezones

# ============================================================
# CALENDAR STATE
# ============================================================

today = datetime.now()
calendar_year = today.year
calendar_month = today.month

# ============================================================
# TIMING / STATE
# ============================================================

START_TIME = time.time()
STATUS_INTERVAL = 15

STATUS_MESSAGES = [
    "TIME SYNCED",
    "CALENDAR ONLINE",
    "IBM MODE",
    "SYSTEM READY",
    "STANDBY",
]

LEFT_HINTS = [
    "TAB:CALENDAR T:12/24H C:COLOR",
    "1-9:TOGGLE TIMEZONE 0:RESET",
    "CTRL+C TO EXIT",
]

CALENDAR_HINTS = "H/L:MONTH  J/K:YEAR"
PROJECT_NAME = "Fausse Nostalgie v1.0"

# ============================================================
# ANSI
# ============================================================

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
REVERSE = "\033[7m"

# ============================================================
# COLOR PALETTES
# ============================================================

PALETTES = {
    "red":        {"FG": "\033[38;2;255;80;80m",   "BG": "\033[48;2;0;0;0m"},
    "amber":     {"FG": "\033[38;2;255;180;0m",   "BG": "\033[48;2;0;0;0m"},
    "green":     {"FG": "\033[38;2;0;255;100m",   "BG": "\033[48;2;0;0;0m"},
    "ice_blue":  {"FG": "\033[38;2;120;220;255m", "BG": "\033[48;2;0;0;0m"},
    "dark_blue": {"FG": "\033[38;2;80;140;220m",  "BG": "\033[48;2;0;0;0m"},
    "dark_green":{"FG": "\033[38;2;0;180;80m",    "BG": "\033[48;2;0;0;0m"},
    "grey":      {"FG": "\033[38;2;180;180;180m", "BG": "\033[48;2;0;0;0m"},
    "white":     {"FG": "\033[38;2;240;240;240m", "BG": "\033[48;2;0;0;0m"},
}

PALETTE_ORDER = [
    "red",
    "amber",
    "green",
    "ice_blue",
    "dark_blue",
    "dark_green",
    "grey",
    "white",
]

palette_index = 2  # green default

def apply_palette():
    global FG, BG
    name = PALETTE_ORDER[palette_index]
    FG = PALETTES[name]["FG"]
    BG = PALETTES[name]["BG"]

apply_palette()

# ============================================================
# LAYOUT
# ============================================================

PADDING = 2
CENTER_BLOCK_WIDTH = 24

# ============================================================
# TERMINAL CONTROL
# ============================================================

HOME = "\033[H"
CLEAR_SCREEN = "\033[2J"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
ENTER_ALT_SCREEN = "\033[?1049h"
EXIT_ALT_SCREEN = "\033[?1049l"
ENABLE_MOUSE = "\033[?1000h"
DISABLE_MOUSE = "\033[?1000l"

# ============================================================
# FIGLET CACHE
# ============================================================

figlet_cache = {}

def get_figlet(text):
    """Cache pyfiglet output for performance"""
    if text not in figlet_cache:
        figlet_cache[text] = pyfiglet.figlet_format(text, font="big")
    return figlet_cache[text]

# ============================================================
# RAW MODE
# ============================================================

old_terminal_settings = None

def enable_raw_mode():
    global old_terminal_settings
    fd = sys.stdin.fileno()
    old_terminal_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    return old_terminal_settings

def disable_raw_mode(old):
    if old:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)

def cleanup():
    """Guaranteed cleanup on exit"""
    disable_raw_mode(old_terminal_settings)
    print(RESET + SHOW_CURSOR + DISABLE_MOUSE + EXIT_ALT_SCREEN, flush=True)

# ============================================================
# RESIZE HANDLER
# ============================================================

needs_redraw = True

def handle_resize(signum, frame):
    global term_width, term_height, needs_redraw
    try:
        term_width, term_height = shutil.get_terminal_size()
    except:
        term_width, term_height = 80, 24
    needs_redraw = True

# ============================================================
# HELPERS
# ============================================================

def get_time_in_tz(tz):
    """Get current time in specified timezone"""
    if tz is None:
        return datetime.now()
    return datetime.now(tz)

def format_time_tz(tz):
    """Format time for a specific timezone"""
    dt = get_time_in_tz(tz)
    if USE_24H:
        return dt.strftime("%H:%M:%S")
    else:
        return dt.strftime("%I:%M:%S %p")

def format_time():
    """Format local time"""
    return format_time_tz(None)

def get_header_title():
    return PROJECT_NAME if int(time.time() - START_TIME) % 300 < 10 else "SYSTEM CLOCK"

def get_status_message():
    return STATUS_MESSAGES[int(time.time() // STATUS_INTERVAL) % len(STATUS_MESSAGES)]

def get_left_hint():
    return LEFT_HINTS[int(time.time() // STATUS_INTERVAL) % len(LEFT_HINTS)]

def get_local_gmt():
    offset = -time.altzone if time.localtime().tm_isdst and time.daylight else -time.timezone
    return f"GMT{offset // 3600:+03d}"

# ============================================================
# DRAWING PRIMITIVES (BUILD TO BUFFER)
# ============================================================

def draw_top_border(w, buf):
    buf.append(BG + FG + "+" + "-" * w + "+" + RESET + "\n")

def draw_bottom_border(w, buf):
    buf.append(BG + FG + "+" + "-" * w + "+" + RESET + "\n")

def print_frame_line(c, w, buf):
    buf.append(BG + FG + "|" + c.ljust(w) + "|" + RESET + "\n")

def draw_separator(w, buf):
    print_frame_line("-" * w, w, buf)

def draw_empty_line(w, buf):
    print_frame_line("", w, buf)

def print_title(t, w, buf):
    buf.append(BG + FG + "|" + BOLD + t.center(w) + FG + "|" + RESET + "\n")

# ============================================================
# STATUS BAR
# ============================================================

def draw_status_bar(left, center, right, w, buf):
    sep = "||"
    pad = " " * PADDING
    inner = w - PADDING * 2

    cs = (inner - CENTER_BLOCK_WIDTH) // 2
    ce = cs + CENTER_BLOCK_WIDTH

    left_area = cs - len(sep)
    right_area = inner - ce - len(sep)

    l = left[:left_area].ljust(left_area)
    c = center[:CENTER_BLOCK_WIDTH].center(CENTER_BLOCK_WIDTH)
    r = right[:right_area].rjust(right_area)

    line = pad + l + sep + c + sep + r + pad

    buf.append(BG + FG + "|" + line + "|" + RESET + "\n")

# ============================================================
# DIGITAL FACE
# ============================================================

def draw_digital_face(clock_ascii, w, buf):
    SIDE = 6
    INNER = w - SIDE * 2
    lines = clock_ascii.splitlines()

    print_frame_line("", w, buf)
    print_frame_line(" " * SIDE + "+" + "-" * (INNER - 2) + "+", w, buf)

    for _ in range(2):
        print_frame_line(" " * SIDE + "|" + " " * (INNER - 2) + "|", w, buf)

    for l in lines:
        print_frame_line(" " * SIDE + "|" + l.center(INNER - 2) + "|", w, buf)

    for _ in range(2):
        print_frame_line(" " * SIDE + "|" + " " * (INNER - 2) + "|", w, buf)

    print_frame_line(" " * SIDE + "+" + "-" * (INNER - 2) + "+", w, buf)
    print_frame_line("", w, buf)

# ============================================================
# TIMEZONE DISPLAY
# ============================================================

def draw_timezones(w, buf):
    """Draw additional timezone clocks below main clock"""
    if len(active_timezones) == 0:
        return  # No extra timezones

    # Draw separator before timezones
    draw_separator(w, buf)

    # Calculate layout for timezone boxes
    tz_count = len(active_timezones)
    box_width = (w - 4 - (tz_count - 1) * 2) // tz_count  # Space for boxes and gaps

    if box_width < 18:  # Minimum readable width
        # If too many timezones, show them in a compact list
        for idx in active_timezones:
            tz_info = TIMEZONES[idx]
            time_str = format_time_tz(tz_info["tz"])
            line = f"  {tz_info['name']}: {time_str} ({tz_info['gmt']})"
            print_frame_line(line.center(w), w, buf)
    else:
        # Draw boxes side by side
        for i in range(3):  # 3 lines per timezone box
            line_parts = []
            for idx in active_timezones:
                tz_info = TIMEZONES[idx]
                if i == 0:
                    content = tz_info["name"].center(box_width - 2)
                elif i == 1:
                    time_str = format_time_tz(tz_info["tz"])
                    content = time_str.center(box_width - 2)
                else:
                    content = tz_info["gmt"].center(box_width - 2)

                line_parts.append("[" + content + "]")

            combined = "  ".join(line_parts)
            print_frame_line(combined.center(w), w, buf)

# ============================================================
# SCREENS
# ============================================================

def draw_header_line(buf):
    date = time.strftime("%d/%m/%Y")
    weekday = time.strftime("%A")
    hour = format_time()

    left = f"  DATE : {date}"
    center = weekday.center(BASE_WIDTH)
    right = hour.rjust(BASE_WIDTH)

    line = list(" " * BASE_WIDTH)
    line[:len(left)] = left
    start = (BASE_WIDTH - len(weekday)) // 2
    line[start:start + len(weekday)] = weekday
    line[-len(hour):] = hour

    print_frame_line("".join(line), BASE_WIDTH, buf)

def draw_clock(buf):
    draw_top_border(BASE_WIDTH, buf)
    print_title(get_header_title(), BASE_WIDTH, buf)
    draw_separator(BASE_WIDTH, buf)
    draw_header_line(buf)
    draw_separator(BASE_WIDTH, buf)

    # Main clock face (always shows local time)
    time_str = format_time().split()[0]  # Remove AM/PM for display
    draw_digital_face(get_figlet(time_str), BASE_WIDTH, buf)

    # Additional timezones if any
    draw_timezones(BASE_WIDTH, buf)

    # SINGLE bottom bar - shows timezone count or local GMT
    draw_separator(BASE_WIDTH, buf)

    if len(active_timezones) > 0:
        # Show list of active timezone names
        tz_names = [TIMEZONES[i]["name"] for i in active_timezones]
        center_text = " + ".join(tz_names[:3])  # Max 3 names
        if len(center_text) > CENTER_BLOCK_WIDTH:
            center_text = f"{len(active_timezones)} ZONES ACTIVE"
    else:
        center_text = get_local_gmt()

    draw_status_bar(get_left_hint(), center_text, get_status_message(), BASE_WIDTH, buf)
    draw_bottom_border(BASE_WIDTH, buf)

def draw_calendar(buf):
    draw_top_border(BASE_WIDTH, buf)
    print_title(f"CALENDAR {calendar_month:02d}/{calendar_year}", BASE_WIDTH, buf)
    draw_separator(BASE_WIDTH, buf)
    draw_header_line(buf)
    draw_separator(BASE_WIDTH, buf)

    # Generate calendar
    cal = calendar.Calendar(calendar.MONDAY).monthdayscalendar(calendar_year, calendar_month)

    # Build calendar lines
    header_line = " Mo | Tu | We | Th | Fr | Sa | Su "
    separator_line = "-" * 29

    # Build week lines
    week_lines = []
    for week in cal:
        week_parts = []
        for day in week:
            if day == 0:
                week_parts.append("  ")
            else:
                week_parts.append(f"{day:2d}")
        week_lines.append(" | ".join(week_parts))

    # Combine all calendar lines
    lines = [header_line, separator_line] + week_lines

    # FIXED: Calculate padding to prevent overflow
    total_calendar_lines = len(lines)
    available_space = 18  # Fixed space for calendar content

    if total_calendar_lines > available_space:
        top_pad = 0
        bottom_pad = 0
    else:
        top_pad = (available_space - total_calendar_lines) // 2
        bottom_pad = available_space - total_calendar_lines - top_pad

    # Draw top padding
    for _ in range(top_pad):
        draw_empty_line(BASE_WIDTH, buf)

    # Draw calendar
    for l in lines:
        print_frame_line(l.center(BASE_WIDTH), BASE_WIDTH, buf)

    # Draw bottom padding
    for _ in range(bottom_pad):
        draw_empty_line(BASE_WIDTH, buf)

    draw_separator(BASE_WIDTH, buf)
    draw_status_bar("TAB TO CLOCK", "CALENDAR MODE", CALENDAR_HINTS, BASE_WIDTH, buf)
    draw_bottom_border(BASE_WIDTH, buf)

# ============================================================
# MAIN LOOP
# ============================================================

def main():
    global current_mode, USE_24H, palette_index
    global calendar_month, calendar_year, needs_redraw
    global active_timezones

    old = enable_raw_mode()
    atexit.register(cleanup)
    signal.signal(signal.SIGWINCH, handle_resize)

    try:
        print(ENTER_ALT_SCREEN + HIDE_CURSOR + ENABLE_MOUSE, end="", flush=True)
        last = time.time()

        while True:
            now = time.time()

            # Redraw periodically or when required
            if needs_redraw or now - last >= 1:
                # Clear cache periodically to prevent memory bloat
                if len(figlet_cache) > 100:
                    figlet_cache.clear()

                # BUILD ENTIRE FRAME IN MEMORY (prevents blinking)
                # FIX: Added CLEAR_SCREEN to prevent ghosting of old content
                buffer = [HOME, CLEAR_SCREEN]

                if current_mode == MODE_CLOCK:
                    draw_clock(buffer)
                else:
                    draw_calendar(buffer)

                # WRITE ENTIRE FRAME AT ONCE (atomic operation)
                print("".join(buffer), end="", flush=True)

                needs_redraw = False
                last = now

            # Check keyboard input
            if select.select([sys.stdin], [], [], 0)[0]:
                try:
                    k = sys.stdin.read(1)
                except (UnicodeDecodeError, IOError):
                    continue

                # Toggle between Clock and Calendar
                if k == "\t":
                    current_mode = MODE_CALENDAR if current_mode == MODE_CLOCK else MODE_CLOCK
                    needs_redraw = True

                # Toggle 12h / 24h time format
                elif k == "t":
                    USE_24H = not USE_24H
                    needs_redraw = True

                # Cycle colour palettes
                elif k == "c":
                    palette_index = (palette_index + 1) % len(PALETTE_ORDER)
                    apply_palette()
                    needs_redraw = True

                # Timezone selection (1-9 to toggle, 0 to reset)
                elif k == "0":
                    # Reset to no extra timezones
                    active_timezones = []
                    needs_redraw = True

                elif k.isdigit() and k != "0":
                    tz_idx = int(k) - 1  # 1->0, 2->1, ... 9->8
                    if tz_idx < len(TIMEZONES):
                        # Toggle timezone: add if not present, remove if present
                        if tz_idx in active_timezones:
                            active_timezones.remove(tz_idx)
                        else:
                            # Max 3 timezones for clean display
                            if len(active_timezones) < 3:
                                active_timezones.append(tz_idx)
                                active_timezones.sort()  # Keep them in order
                        needs_redraw = True

                # Calendar navigation
                elif current_mode == MODE_CALENDAR:
                    if k == "h":
                        calendar_month -= 1
                        needs_redraw = True
                    elif k == "l":
                        calendar_month += 1
                        needs_redraw = True
                    elif k == "j":
                        calendar_year -= 1
                        needs_redraw = True
                    elif k == "k":
                        calendar_year += 1
                        needs_redraw = True

                    if calendar_month < 1:
                        calendar_month = 12
                        calendar_year -= 1
                    elif calendar_month > 12:
                        calendar_month = 1
                        calendar_year += 1

            time.sleep(0.05)  # Avoid excessive CPU

    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()

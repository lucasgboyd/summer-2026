#!/usr/bin/env python3
"""
Generate trip.ics (an iCalendar feed) from schedule.md.

Run this whenever schedule.md changes:
    python3 generate_calendar.py

Then commit + push trip.ics. Google Calendar (subscribed via URL) will
refresh it automatically on its own cadence (~8-24 hrs).

All events are all-day events. Two kinds are produced:
  * "Stay" events  - one banner per run of consecutive days in the same Location.
  * "Event" events - one per notable Activity (weddings, concert, flights, etc.).
"""

import re
import hashlib
from datetime import date, timedelta

YEAR = 2026
SCHEDULE = "schedule.md"
OUTPUT = "trip.ics"

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_date(text):
    """Turn 'Wed Jul 1' into a date(2026, 7, 1)."""
    m = re.search(r"([A-Z][a-z]{2})\s+(\d{1,2})", text)
    if not m:
        return None
    mon, day = m.group(1), int(m.group(2))
    if mon not in MONTHS:
        return None
    return date(YEAR, MONTHS[mon], day)


def parse_schedule(path):
    """Read the markdown tables and return a list of day dicts."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 7:
                continue
            # skip header + separator rows
            if cells[0].lower() == "date" or set(cells[0]) <= set("-: "):
                continue
            d = parse_date(cells[0])
            if not d:
                continue
            rows.append({
                "date": d,
                "location": cells[1],
                "lodging": cells[2],
                "activity": cells[3],
                "driving": cells[4],
                "notes": cells[6],
            })
    rows.sort(key=lambda r: r["date"])
    return rows


def uid(*parts):
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:12]
    return f"{h}@summer-2026"


def fmt(d):
    return d.strftime("%Y%m%d")


def esc(text):
    return (text.replace("\\", "\\\\").replace(",", "\\,")
                .replace(";", "\\;").replace("\n", "\\n"))


def all_day_event(start, end_inclusive, summary, description=""):
    """end_inclusive is the last day the event covers; DTEND is exclusive."""
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid(start, summary)}",
        "DTSTAMP:20260101T000000Z",
        f"DTSTART;VALUE=DATE:{fmt(start)}",
        f"DTEND;VALUE=DATE:{fmt(end_inclusive + timedelta(days=1))}",
        f"SUMMARY:{esc(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{esc(description)}")
    lines.append("TRANSP:TRANSPARENT")
    lines.append("END:VEVENT")
    return lines


def group_runs(rows, key):
    """Yield (start_date, end_date, list_of_rows) for consecutive equal keys."""
    run = []
    for r in rows:
        k = key(r)
        if not k:
            if run:
                yield run[0]["date"], run[-1]["date"], run
                run = []
            continue
        if run and key(run[-1]) == k and (r["date"] - run[-1]["date"]).days == 1:
            run.append(r)
        else:
            if run:
                yield run[0]["date"], run[-1]["date"], run
            run = [r]
    if run:
        yield run[0]["date"], run[-1]["date"], run


def normalize_activity(text):
    """Collapse e.g. 'Backpacking (Day 1)' so consecutive days group together."""
    if not text:
        return ""
    if "backpacking" in text.lower():
        return "Sierra backpacking"
    return text


def build():
    rows = parse_schedule(SCHEDULE)

    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Summer 2026//Trip Planner//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Summer 2026 — Lucas & Carly",
        "X-WR-TIMEZONE:America/Los_Angeles",
    ]

    # Stay events: group consecutive days in the same Location.
    for start, end, run in group_runs(rows, lambda r: r["location"]):
        loc = run[0]["location"]
        lodgings = [r["lodging"] for r in run if r["lodging"]]
        unique_lodging = sorted(set(lodgings))
        summary = loc
        if len(unique_lodging) == 1:
            summary = f"{loc} — {unique_lodging[0]}"
        desc_bits = []
        if unique_lodging:
            desc_bits.append("Lodging: " + "; ".join(unique_lodging))
        notes = sorted({r["notes"] for r in run if r["notes"]})
        if notes:
            desc_bits.append("Notes: " + "; ".join(notes))
        out += all_day_event(start, end, summary, "\n".join(desc_bits))

    # Activity events: group consecutive days with the same (normalized) activity.
    for start, end, run in group_runs(rows, lambda r: normalize_activity(r["activity"])):
        act = normalize_activity(run[0]["activity"])
        if not act:
            continue
        out += all_day_event(start, end, act, "")

    out.append("END:VCALENDAR")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\r\n".join(out) + "\r\n")

    n_events = sum(1 for line in out if line == "BEGIN:VEVENT")
    print(f"Wrote {OUTPUT} with {n_events} events from {len(rows)} schedule days.")


if __name__ == "__main__":
    build()

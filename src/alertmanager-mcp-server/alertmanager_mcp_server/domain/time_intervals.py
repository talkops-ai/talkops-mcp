"""Alertmanager `time_intervals` / `mute_time_intervals` / `active_time_intervals` evaluator.

Implements Alertmanager `timeinterval` package semantics:
- Named time intervals contain a list of `TimeInterval` entries (OR-ed together)
- Each `TimeInterval` entry specifies optional `times`, `weekdays`, `days_of_month`,
  `months`, `years`, and `location` (AND-ed together within an entry)
- Supports ranges (`monday:friday`, `1:15`, `-3:-1`, `january:march`, `2025:2027`)
  and `24:00` end-of-day time boundaries.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_WEEKDAY_MAP: dict[str, int] = {
    "sunday": 0,
    "sun": 0,
    "0": 0,
    "monday": 1,
    "mon": 1,
    "1": 1,
    "tuesday": 2,
    "tue": 2,
    "2": 2,
    "wednesday": 3,
    "wed": 3,
    "3": 3,
    "thursday": 4,
    "thu": 4,
    "4": 4,
    "friday": 5,
    "fri": 5,
    "5": 5,
    "saturday": 6,
    "sat": 6,
    "6": 6,
}

_MONTH_MAP: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "1": 1,
    "february": 2,
    "feb": 2,
    "2": 2,
    "march": 3,
    "mar": 3,
    "3": 3,
    "april": 4,
    "apr": 4,
    "4": 4,
    "may": 5,
    "5": 5,
    "june": 6,
    "jun": 6,
    "6": 6,
    "july": 7,
    "jul": 7,
    "7": 7,
    "august": 8,
    "aug": 8,
    "8": 8,
    "september": 9,
    "sep": 9,
    "9": 9,
    "october": 10,
    "oct": 10,
    "10": 10,
    "november": 11,
    "nov": 11,
    "11": 11,
    "december": 12,
    "dec": 12,
    "12": 12,
}


def _parse_hhmm(value: str) -> int:
    """Parse 'HH:MM' into minutes since 00:00 (0..1440)."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time boundary '{value}', expected HH:MM.")
    hour, minute = int(parts[0]), int(parts[1])
    if hour == 24 and minute == 0:
        return 1440
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time '{value}' out of range (00:00..24:00).")
    return hour * 60 + minute


def _match_time_ranges(dt: datetime, times: Sequence[Mapping[str, Any]]) -> bool:
    """Return True if `dt` falls within at least one `{start_time, end_time}` window."""
    if not times:
        return True
    current_mins = dt.hour * 60 + dt.minute + (dt.second / 60.0)
    for item in times:
        start_raw = str(item.get("start_time", "00:00"))
        end_raw = str(item.get("end_time", "24:00"))
        start_mins = _parse_hhmm(start_raw)
        end_mins = _parse_hhmm(end_raw)
        # In Alertmanager, start_time is inclusive and end_time is exclusive
        if start_mins <= current_mins < end_mins:
            return True
    return False


def _match_weekdays(dt: datetime, weekdays: Sequence[Any]) -> bool:
    """Return True if `dt` weekday matches at least one weekday token/range."""
    if not weekdays:
        return True
    # Convert Python weekday (Mon=0..Sun=6) to Go/Alertmanager weekday (Sun=0..Sat=6)
    am_wday = (dt.weekday() + 1) % 7
    for raw in weekdays:
        token = str(raw).strip().lower()
        if ":" in token:
            left_s, right_s = token.split(":", 1)
            left = _WEEKDAY_MAP[left_s.strip()]
            right = _WEEKDAY_MAP[right_s.strip()]
            if left <= right:
                if left <= am_wday <= right:
                    return True
            else:
                # Wrapped range e.g. friday:monday
                if am_wday >= left or am_wday <= right:
                    return True
        else:
            if am_wday == _WEEKDAY_MAP[token]:
                return True
    return False


def _resolve_dom(val: int, days_in_month: int) -> int:
    """Resolve negative day-of-month offsets (e.g. -1 -> last day of month)."""
    if val < 0:
        return days_in_month + 1 + val
    return val


def _match_days_of_month(dt: datetime, days_of_month: Sequence[Any]) -> bool:
    """Return True if `dt.day` matches at least one day-of-month spec."""
    if not days_of_month:
        return True
    days_in_month = calendar.monthrange(dt.year, dt.month)[1]
    for raw in days_of_month:
        token = str(raw).strip()
        if ":" in token:
            left_s, right_s = token.split(":", 1)
            left = _resolve_dom(int(left_s.strip()), days_in_month)
            right = _resolve_dom(int(right_s.strip()), days_in_month)
            if left <= dt.day <= right:
                return True
        else:
            if dt.day == _resolve_dom(int(token), days_in_month):
                return True
    return False


def _match_months(dt: datetime, months: Sequence[Any]) -> bool:
    """Return True if `dt.month` matches at least one month token/range."""
    if not months:
        return True
    for raw in months:
        token = str(raw).strip().lower()
        if ":" in token:
            left_s, right_s = token.split(":", 1)
            left = _MONTH_MAP[left_s.strip()]
            right = _MONTH_MAP[right_s.strip()]
            if left <= dt.month <= right:
                return True
        else:
            if dt.month == _MONTH_MAP[token]:
                return True
    return False


def _match_years(dt: datetime, years: Sequence[Any]) -> bool:
    """Return True if `dt.year` matches at least one year token/range."""
    if not years:
        return True
    for raw in years:
        token = str(raw).strip()
        if ":" in token:
            left_s, right_s = token.split(":", 1)
            if int(left_s.strip()) <= dt.year <= int(right_s.strip()):
                return True
        else:
            if dt.year == int(token):
                return True
    return False


def matches_time_interval_entry(
    entry: Mapping[str, Any],
    at_time: datetime,
) -> bool:
    """Return True if `at_time` matches a single `time_intervals` list element."""
    loc_name = str(entry.get("location") or "UTC").strip()
    try:
        tz = ZoneInfo(loc_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc

    if at_time.tzinfo is None:
        at_time = at_time.replace(tzinfo=timezone.utc)
    local_dt = at_time.astimezone(tz)

    times = entry.get("times") or []
    weekdays = entry.get("weekdays") or []
    days_of_month = entry.get("days_of_month") or []
    months = entry.get("months") or []
    years = entry.get("years") or []

    return (
        _match_time_ranges(local_dt, times)
        and _match_weekdays(local_dt, weekdays)
        and _match_days_of_month(local_dt, days_of_month)
        and _match_months(local_dt, months)
        and _match_years(local_dt, years)
    )


@dataclass(frozen=True)
class TimeIntervalCatalog:
    """Catalog of named `time_intervals` and `mute_time_intervals` from Alertmanager config."""

    intervals: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @classmethod
    def from_config(cls, raw_config: Mapping[str, Any]) -> "TimeIntervalCatalog":
        """Build catalog from top-level `time_intervals` and `mute_time_intervals` sections."""
        catalog: dict[str, list[dict[str, Any]]] = {}
        for section_key in ("time_intervals", "mute_time_intervals"):
            items = raw_config.get(section_key)
            if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
                for item in items:
                    if isinstance(item, Mapping):
                        name = str(item.get("name", "")).strip()
                        entries = item.get("time_intervals")
                        if name and isinstance(entries, Sequence):
                            catalog[name] = [
                                dict(e) for e in entries if isinstance(e, Mapping)
                            ]
        return cls(intervals=catalog)

    def is_interval_active(self, name: str, at_time: datetime) -> bool:
        """Return True if the named interval exists and contains `at_time`."""
        entries = self.intervals.get(name)
        if not entries:
            return False
        return any(matches_time_interval_entry(entry, at_time) for entry in entries)

    def evaluate_route_intervals(
        self,
        *,
        active_time_intervals: Sequence[str],
        mute_time_intervals: Sequence[str],
        at_time: datetime,
    ) -> tuple[bool, list[str]]:
        """Evaluate whether a route is muted at `at_time`.

        Returns:
            `(is_muted, reasons)` where `is_muted` is True if the route suppresses
            notifications at `at_time`, and `reasons` lists the interval names
            causing the suppression.
        """
        reasons: list[str] = []

        if active_time_intervals:
            active_matches = [
                name
                for name in active_time_intervals
                if self.is_interval_active(name, at_time)
            ]
            if not active_matches:
                reasons.append(
                    "outside active_time_intervals: "
                    + ", ".join(active_time_intervals)
                )

        if mute_time_intervals:
            muted_matches = [
                name
                for name in mute_time_intervals
                if self.is_interval_active(name, at_time)
            ]
            if muted_matches:
                reasons.append(
                    "inside mute_time_intervals: " + ", ".join(muted_matches)
                )

        return (len(reasons) > 0, reasons)

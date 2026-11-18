"""Unit tests for `alertmanager_mcp_server.domain.time_intervals`."""

from __future__ import annotations

from datetime import datetime, timezone

from alertmanager_mcp_server.domain.time_intervals import (
    TimeIntervalCatalog,
    matches_time_interval_entry,
)


class TestTimeIntervals:
    def test_weekday_and_time_range_with_timezone(self) -> None:
        entry = {
            "weekdays": ["monday:friday"],
            "times": [{"start_time": "09:00", "end_time": "17:00"}],
            "location": "America/New_York",
        }
        # Wednesday 14:00 UTC is 10:00 EDT -> inside business hours
        inside_dt = datetime(2026, 3, 25, 14, 0, tzinfo=timezone.utc)
        assert matches_time_interval_entry(entry, inside_dt) is True

        # Wednesday 22:00 UTC is 18:00 EDT -> outside business hours
        outside_dt = datetime(2026, 3, 25, 22, 0, tzinfo=timezone.utc)
        assert matches_time_interval_entry(entry, outside_dt) is False

    def test_negative_day_of_month_and_month_ranges(self) -> None:
        # Last day of March (-1 -> 31)
        entry = {
            "days_of_month": ["-1"],
            "months": ["january:march"],
            "years": ["2025:2027"],
            "times": [{"start_time": "00:00", "end_time": "24:00"}],
        }
        march_31 = datetime(2026, 3, 31, 23, 30, tzinfo=timezone.utc)
        assert matches_time_interval_entry(entry, march_31) is True

        march_30 = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
        assert matches_time_interval_entry(entry, march_30) is False

    def test_catalog_evaluate_active_and_mute_intervals(self) -> None:
        cfg = {
            "time_intervals": [
                {
                    "name": "weekends",
                    "time_intervals": [{"weekdays": ["saturday", "sunday"]}],
                },
                {
                    "name": "workhours",
                    "time_intervals": [
                        {
                            "weekdays": ["monday:friday"],
                            "times": [{"start_time": "09:00", "end_time": "17:00"}],
                        }
                    ],
                },
            ]
        }
        catalog = TimeIntervalCatalog.from_config(cfg)

        # Saturday 10:00 UTC: muted by `weekends` AND outside `workhours`
        sat = datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc)
        muted, reasons = catalog.evaluate_route_intervals(
            active_time_intervals=["workhours"],
            mute_time_intervals=["weekends"],
            at_time=sat,
        )
        assert muted is True
        assert len(reasons) == 2

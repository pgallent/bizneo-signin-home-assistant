"""Tests for deterministic schedule and payload behavior."""

from __future__ import annotations

import random
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.bizneo_signin.const import DEFAULT_OPTIONS, PauseType
from custom_components.bizneo_signin.models import WorkSession
from custom_components.bizneo_signin.schedule import (
    ScheduleError,
    build_payload,
    complete_missing_pauses,
    create_pause,
    is_working_day,
    parse_non_working_dates,
)

TZ = ZoneInfo("Europe/Madrid")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=TZ)


class FirstChoice(random.Random):
    def choice(self, values):
        return values[0]


class LastChoice(random.Random):
    def choice(self, values):
        return values[-1]


class ScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.options = dict(DEFAULT_OPTIONS)
        self.options.update(
            {
                "entry_window_start": "07:50",
                "entry_window_end": "08:10",
                "exit_window_start": "16:20",
                "exit_window_end": "16:40",
                "short_pause_window_start": "10:00",
                "short_pause_window_end": "11:45",
                "long_pause_window_start": "13:30",
                "long_pause_window_end": "14:30",
            }
        )

    def test_acceptance_payload_keeps_original_crossing_times(self):
        session = WorkSession(
            work_date="2026-03-02",
            entry_at=at("2026-03-02T07:58:00"),
            exit_at=at("2026-03-02T16:32:00"),
        )
        session.pauses.append(
            create_pause(
                session, PauseType.SHORT, at("2026-03-02T11:03:00"), self.options, FirstChoice()
            )
        )
        session.pauses.append(
            create_pause(
                session, PauseType.LONG, at("2026-03-02T14:01:00"), self.options, FirstChoice()
            )
        )

        payload = build_payload(session, self.options)

        hours = payload["logged_time"]["logged_hours"]
        self.assertEqual(payload["logged_time"]["date"], "2026-03-02")
        self.assertEqual(hours[0]["start_at"], "07:58:00")
        self.assertEqual(hours[-1]["end_at"], "16:32:00")
        self.assertEqual(len(hours), 3)

    def test_missing_pauses_are_generated_deterministically(self):
        session = WorkSession(
            work_date="2026-03-02",
            entry_at=at("2026-03-02T07:58:00"),
            exit_at=at("2026-03-02T16:32:00"),
        )

        pauses = complete_missing_pauses(session, self.options, FirstChoice())

        self.assertEqual([pause.kind for pause in pauses], [PauseType.SHORT, PauseType.LONG])
        self.assertTrue(all(pause.generated for pause in pauses))
        self.assertEqual(pauses[0].start.strftime("%H:%M"), "10:00")
        self.assertEqual(pauses[1].start.strftime("%H:%M"), "13:30")

    def test_friday_requires_only_long_pause(self):
        session = WorkSession(
            work_date="2026-03-06",
            entry_at=at("2026-03-06T07:58:00"),
            exit_at=at("2026-03-06T15:02:00"),
        )

        pauses = complete_missing_pauses(session, self.options, FirstChoice())

        self.assertEqual([pause.kind for pause in pauses], [PauseType.LONG])
        with self.assertRaisesRegex(ScheduleError, "viernes"):
            create_pause(
                session,
                PauseType.SHORT,
                at("2026-03-06T11:00:00"),
                self.options,
                FirstChoice(),
            )

    def test_explicit_rests_are_added_to_one_payload(self):
        self.options.update({"pauses_as_rest": True, "short_rest_id": 101, "long_rest_id": 202})
        session = WorkSession(
            work_date="2026-03-02",
            entry_at=at("2026-03-02T08:00:00"),
            exit_at=at("2026-03-02T16:30:00"),
        )
        session.pauses = complete_missing_pauses(session, self.options, FirstChoice())

        hours = build_payload(session, self.options)["logged_time"]["logged_hours"]

        self.assertEqual(len(hours), 5)
        self.assertEqual([part["rest"] for part in hours if "rest" in part], [101, 202])

    def test_duplicate_and_out_of_window_pause_are_rejected(self):
        session = WorkSession(
            work_date="2026-03-02",
            entry_at=at("2026-03-02T08:00:00"),
            exit_at=at("2026-03-02T16:30:00"),
        )
        session.pauses.append(
            create_pause(
                session, PauseType.SHORT, at("2026-03-02T11:00:00"), self.options, FirstChoice()
            )
        )
        with self.assertRaisesRegex(ScheduleError, "ya está registrada"):
            create_pause(
                session, PauseType.SHORT, at("2026-03-02T11:10:00"), self.options, FirstChoice()
            )
        with self.assertRaisesRegex(ScheduleError, "fuera"):
            create_pause(
                session, PauseType.LONG, at("2026-03-02T12:00:00"), self.options, FirstChoice()
            )

    def test_non_working_dates_and_fake_holiday(self):
        self.options["non_working_dates"] = "2026-03-03, 2026-04-06..2026-04-10"
        self.assertEqual(len(parse_non_working_dates(self.options["non_working_dates"])), 6)
        self.assertFalse(is_working_day(at("2026-03-03T08:00:00").date(), self.options))

        class FakeHolidays:
            @staticmethod
            def Spain(**kwargs):
                return {at("2026-03-04T08:00:00").date(): "Festivo"}

        self.options["community"] = "VC"
        self.assertFalse(
            is_working_day(at("2026-03-04T08:00:00").date(), self.options, FakeHolidays)
        )

    def test_reversed_non_working_range_is_rejected(self):
        with self.assertRaisesRegex(ScheduleError, "al revés"):
            parse_non_working_dates("2026-04-10..2026-04-01")

    def test_payload_rejects_an_overnight_session(self):
        session = WorkSession(
            work_date="2026-03-02",
            entry_at=at("2026-03-02T22:00:00"),
            exit_at=at("2026-03-03T06:00:00"),
        )
        with self.assertRaisesRegex(ScheduleError, "mismo día"):
            build_payload(session, self.options)


if __name__ == "__main__":
    unittest.main()

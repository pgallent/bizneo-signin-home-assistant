"""Tests for restart-safe serialization."""

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.bizneo_signin.const import PauseType, SigninState
from custom_components.bizneo_signin.models import Pause, WorkSession


class ModelTests(unittest.TestCase):
    def test_round_trip_preserves_pending_crossings_and_payload(self):
        timezone = ZoneInfo("Europe/Madrid")
        start = datetime(2026, 3, 2, 7, 58, tzinfo=timezone)
        session = WorkSession(
            state=SigninState.EXIT_PENDING,
            work_date="2026-03-02",
            entry_at=start,
            exit_pending_at=datetime(2026, 3, 2, 16, 32, tzinfo=timezone),
            pauses=[
                Pause(PauseType.SHORT, start.replace(hour=11), start.replace(hour=11, minute=15))
            ],
            payload={"logged_time": {"date": "2026-03-02"}},
        )

        restored = WorkSession.from_dict(session.to_dict())

        self.assertEqual(restored.state, SigninState.EXIT_PENDING)
        self.assertEqual(restored.entry_at, session.entry_at)
        self.assertEqual(restored.exit_pending_at, session.exit_pending_at)
        self.assertEqual(restored.pauses[0].kind, PauseType.SHORT)
        self.assertEqual(restored.payload, session.payload)


if __name__ == "__main__":
    unittest.main()

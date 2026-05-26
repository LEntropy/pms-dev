"""정책 엔진 단위 테스트 — 설치 윈도우, 버전 비교 등 순수 로직."""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone


class TestInstallWindow:
    """is_within_install_window 함수 테스트."""

    def _make_policy(self, window: dict | None):
        p = MagicMock()
        p.install_window = window
        return p

    def _patch_now(self, mocker, weekday: int, hour: int, minute: int = 0, tz: str = "UTC"):
        """현재 시각을 고정 (weekday: 0=Mon … 6=Sun)."""
        from zoneinfo import ZoneInfo
        from app.services.policy_engine import is_within_install_window
        import app.services.policy_engine as eng

        fake_dt = datetime(2026, 5, 25 + weekday, hour, minute, tzinfo=ZoneInfo(tz))
        mocker.patch("app.services.policy_engine.datetime", wraps=datetime)
        # patch datetime.now inside the module
        mocker.patch.object(
            eng, "datetime",
            **{"now.return_value": fake_dt, "side_effect": None},
            wraps=datetime,
        )
        return fake_dt

    def test_no_window_always_allowed(self):
        from app.services.policy_engine import is_within_install_window
        policy = self._make_policy(None)
        assert is_within_install_window(policy) is True

    def test_within_window(self, mocker):
        from app.services.policy_engine import is_within_install_window
        from zoneinfo import ZoneInfo
        import app.services.policy_engine as eng

        # Monday 03:00 UTC, window Mon-Fri 02:00-04:00 UTC
        fake_dt = datetime(2026, 5, 25, 3, 0, tzinfo=ZoneInfo("UTC"))  # Monday
        mocker.patch.object(eng, "datetime", **{"now.return_value": fake_dt}, wraps=datetime)

        policy = self._make_policy({
            "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "start": "02:00",
            "end": "04:00",
            "tz": "UTC",
        })
        assert is_within_install_window(policy) is True

    def test_outside_time_window(self, mocker):
        from app.services.policy_engine import is_within_install_window
        from zoneinfo import ZoneInfo
        import app.services.policy_engine as eng

        # Monday 10:00 UTC — outside 02:00-04:00
        fake_dt = datetime(2026, 5, 25, 10, 0, tzinfo=ZoneInfo("UTC"))
        mocker.patch.object(eng, "datetime", **{"now.return_value": fake_dt}, wraps=datetime)

        policy = self._make_policy({
            "days": ["Mon"],
            "start": "02:00",
            "end": "04:00",
            "tz": "UTC",
        })
        assert is_within_install_window(policy) is False

    def test_outside_day_window(self, mocker):
        from app.services.policy_engine import is_within_install_window
        from zoneinfo import ZoneInfo
        import app.services.policy_engine as eng

        # Saturday 03:00 UTC — day not in Mon-Fri
        fake_dt = datetime(2026, 5, 30, 3, 0, tzinfo=ZoneInfo("UTC"))  # Saturday
        mocker.patch.object(eng, "datetime", **{"now.return_value": fake_dt}, wraps=datetime)

        policy = self._make_policy({
            "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "start": "02:00",
            "end": "04:00",
            "tz": "UTC",
        })
        assert is_within_install_window(policy) is False

    def test_midnight_crossing_window_inside(self, mocker):
        """23:00-01:00 윈도우에서 00:30은 허용되어야 한다."""
        from app.services.policy_engine import is_within_install_window
        from zoneinfo import ZoneInfo
        import app.services.policy_engine as eng

        fake_dt = datetime(2026, 5, 25, 0, 30, tzinfo=ZoneInfo("UTC"))
        mocker.patch.object(eng, "datetime", **{"now.return_value": fake_dt}, wraps=datetime)

        policy = self._make_policy({
            "days": ["Mon"],
            "start": "23:00",
            "end": "01:00",
            "tz": "UTC",
        })
        assert is_within_install_window(policy) is True

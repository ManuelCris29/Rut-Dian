"""Pruebas del reloj y el Sleeper de sistema (T-35)."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from doubles import FakeSleeper, FixedClock, assert_clock_contract

from rut_checker.application.clock import Sleeper, SystemClock, SystemSleeper

BOGOTA = ZoneInfo("America/Bogota")


def test_system_clock_satisfies_contract() -> None:
    assert_clock_contract(SystemClock())


def test_system_clock_now_is_aware_in_bogota() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(hours=-5)
    assert now.tzinfo == BOGOTA


def test_system_sleeper_delegates_to_time_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    waited: list[float] = []
    monkeypatch.setattr("rut_checker.application.clock.time.sleep", waited.append)
    SystemSleeper().sleep(2.5)
    assert waited == [2.5]


def test_doubles_and_system_sleeper_satisfy_protocol() -> None:
    sleepers: list[Sleeper] = [SystemSleeper(), FakeSleeper()]
    assert all(isinstance(s, Sleeper) for s in sleepers)
    assert FixedClock.on(SystemClock().today()).today() == SystemClock().today()

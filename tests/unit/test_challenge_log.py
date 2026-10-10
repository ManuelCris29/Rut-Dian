"""Registro de eventos de desafío (ADR-0003 §3): sumidero hacia el log JSONL y cableado."""

import json
from pathlib import Path

import pytest

from rut_checker.adapters.dian_portal import factory
from rut_checker.domain.status import ChallengeEvent
from rut_checker.infra.log_format import LogEvent
from rut_checker.infra.logging import ChallengeLogSink, close_run_logging, configure_logging

RUN_ID = "20261010-130000-abcd"


def test_challenge_events_are_a_subset_of_the_closed_log_catalog() -> None:
    assert {e.value for e in ChallengeEvent} <= {e.value for e in LogEvent}


def test_sink_writes_closed_events_with_duration_only(tmp_path: Path) -> None:
    sink = ChallengeLogSink()
    sink.bind(configure_logging(RUN_ID, tmp_path))
    try:
        sink(ChallengeEvent.DETECTED, 0)
        sink(ChallengeEvent.RESOLVED, 1500)
        sink(ChallengeEvent.TIMEOUT, 120000)
    finally:
        close_run_logging(RUN_ID)
    lines = [json.loads(x) for x in (tmp_path / f"run_{RUN_ID}.jsonl").read_text().splitlines()]
    assert [x["event"] for x in lines] == [
        "challenge_detected",
        "challenge_resolved",
        "challenge_timeout",
    ]
    assert [x["duration_ms"] for x in lines] == [0, 1500, 120000]
    assert all(set(x) == {"ts", "event", "run_id", "duration_ms"} for x in lines)


def test_unbound_sink_ignores_events() -> None:
    ChallengeLogSink()(ChallengeEvent.DETECTED, 0)  # no lanza ni escribe


def test_factory_passes_the_sink_to_the_source(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class Spy:
        def __init__(self, *args: object, **kwargs: object) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(factory, "DianPortalSource", Spy)
    sink = ChallengeLogSink()
    factory.create_portal_source(object(), object(), object(), object(), sink)  # type: ignore[arg-type]
    assert seen == {"on_challenge": sink}

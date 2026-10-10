"""Espera asistida ante un desafío de seguridad (T-49, ADR-0003 §3).

Todo es PASIVO: solo `wait_for` y `is_visible` sobre el elemento host del desafío en el DOM
principal. Sin clics, foco, entrada ni lectura del frame (la prueba de arquitectura lo exige).

Si el host desaparece y reaparece dentro del mismo plazo, sigue esperando con el tiempo restante y
sin un nuevo aviso: sigue siendo una sola pausa. Los hitos se entregan a un recolector inyectado
(`ChallengeSink`); este módulo no usa loggers ni conoce la fila en curso.
"""

import time
from collections.abc import Callable

from playwright.sync_api import Page

from rut_checker.adapters.dian_portal.detection import (
    PageKind,
    find_challenge,
    run_translated,
    watch_specs,
)
from rut_checker.adapters.dian_portal.models import PortalSelectors
from rut_checker.adapters.dian_portal.waiting import wait_for_any_visible, wait_until_none_visible
from rut_checker.domain.errors import HumanInterventionRequired
from rut_checker.domain.status import ChallengeEvent

__all__ = ["ChallengeSink", "wait_for_human"]

ChallengeSink = Callable[[ChallengeEvent, int], None]
NOTICE = (
    "Se detectó una verificación de seguridad del portal. Resuélvala en la ventana "
    "del navegador; esperando hasta {seconds} s."
)


def _left_ms(deadline: float) -> int:
    return int((deadline - time.monotonic()) * 1000)


def _settled(
    page: Page, selectors: PortalSelectors, expected: frozenset[PageKind], deadline: float
) -> bool:
    """Espera a que el host se oculte y luego a que algo reconocible (o el desafío) se muestre.

    Returns:
        `False` si el desafío siguió visible hasta agotar el plazo.
    """
    markers = selectors.detection.challenge_markers
    if _left_ms(deadline) <= 0:
        return False
    if not run_translated(lambda: wait_until_none_visible(page, markers, _left_ms(deadline))):
        return False
    watched = watch_specs(selectors, expected)
    # Agotar esta espera no es un error: el llamador reclasifica la página.
    run_translated(lambda: wait_for_any_visible(page, watched, max(_left_ms(deadline), 1)))
    return True


def wait_for_human(
    page: Page,
    selectors: PortalSelectors,
    expected: frozenset[PageKind],
    *,
    seconds: int,
    notify: Callable[[str], None],
    emit: ChallengeSink | None,
) -> None:
    """Avisa a la persona y espera pasivamente a que el desafío termine.

    Args:
        seconds: plazo total (`RUT_HUMAN_CHALLENGE_TIMEOUT_S`).
        notify: aviso al operador (mensaje sin identificación).
        emit: recolector de hitos (`DETECTED`, `RESOLVED`, `TIMEOUT`) con los ms transcurridos.

    Raises:
        HumanInterventionRequired: el desafío siguió visible hasta agotar el plazo.
    """
    started = time.monotonic()
    deadline = started + seconds

    def report(event: ChallengeEvent) -> None:
        if emit is not None:
            emit(event, int((time.monotonic() - started) * 1000))

    report(ChallengeEvent.DETECTED)
    notify(NOTICE.format(seconds=seconds))
    while True:
        if not _settled(page, selectors, expected, deadline):
            report(ChallengeEvent.TIMEOUT)
            raise HumanInterventionRequired
        if not run_translated(lambda: find_challenge(page, selectors)):
            report(ChallengeEvent.RESOLVED)
            return

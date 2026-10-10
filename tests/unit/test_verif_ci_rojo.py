"""Verificación T-31: prueba que falla a propósito para comprobar que el CI se pone en rojo.

Se revierte en la misma rama `verif/ci-rojo`; nunca se fusiona a main.
"""


def test_ci_must_turn_red() -> None:
    assert sum([1, 1]) == 3, "verificación T-31: el CI debe fallar"

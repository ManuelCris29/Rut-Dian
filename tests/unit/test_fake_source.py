"""Pruebas de `FakeSource`, los puertos y el doble de operador (T-34)."""

import pytest
from doubles import OperatorDouble

from rut_checker.adapters.fake_source import DEFAULT_RESULT, FakeSource
from rut_checker.domain.errors import (
    InvalidIdentification,
    InvalidReason,
    PortalUnavailable,
    QueryTimeout,
)
from rut_checker.domain.models import IdentificationInput, RutResult
from rut_checker.domain.status import QueryStatus, SourceKind
from rut_checker.ports.operator import OperatorPort
from rut_checker.ports.rut_source import RutSourcePort

ID_1 = "1000000001"
ID_2 = "1000000002"


def _ident(value: str = ID_1) -> IdentificationInput:
    return IdentificationInput(identification=value)


def _ok(estado: str = "CANCELADO") -> RutResult:
    return RutResult(
        status=QueryStatus.EXITOSA,
        source=SourceKind.FAKE,
        estado_rut=estado,
        name="PERSONA FICTICIA UNO",
    )


def test_returns_programmed_result_and_counts_calls() -> None:
    source = FakeSource({ID_1: _ok()})
    assert source.query(_ident()) == _ok()
    assert source.query(_ident()) == _ok()
    assert source.calls_for(ID_1) == 2
    assert source.calls_for(ID_2) == 0
    assert source.total_calls == 2


def test_raises_programmed_exception() -> None:
    source = FakeSource({ID_1: PortalUnavailable})
    with pytest.raises(PortalUnavailable):
        source.query(_ident())
    assert source.calls_for(ID_1) == 1


def test_sequence_is_consumed_in_order_and_last_repeats() -> None:
    source = FakeSource({ID_1: [PortalUnavailable, QueryTimeout, _ok()]})
    with pytest.raises(PortalUnavailable):
        source.query(_ident())
    with pytest.raises(QueryTimeout):
        source.query(_ident())
    assert source.query(_ident()) == _ok()
    assert source.query(_ident()) == _ok()
    assert source.calls_for(ID_1) == 4


def test_unprogrammed_identification_gets_default_success() -> None:
    result = FakeSource().query(_ident(ID_2))
    assert result == DEFAULT_RESULT
    assert (result.status, result.estado_rut, result.name) == (
        QueryStatus.EXITOSA,
        "ACTIVO",
        "PERSONA FICTICIA UNO",
    )


def test_custom_default_can_be_an_exception() -> None:
    with pytest.raises(PortalUnavailable):
        FakeSource(default=PortalUnavailable).query(_ident())


def test_empty_sequence_is_rejected() -> None:
    with pytest.raises(ValueError, match="vacía"):
        FakeSource({ID_1: []})


def test_program_replaces_previous_response() -> None:
    source = FakeSource({ID_1: _ok()})
    source.program(ID_1, PortalUnavailable)
    with pytest.raises(PortalUnavailable):
        source.query(_ident())


def test_kind_paced_and_close_are_configurable_and_idempotent() -> None:
    assert FakeSource().kind is SourceKind.FAKE
    assert FakeSource().paced is False
    assert FakeSource(paced=True).paced is True
    source = FakeSource()
    source.close()
    source.close()
    assert source.close_count == 2


def test_fake_source_satisfies_port() -> None:
    assert isinstance(FakeSource(), RutSourcePort)


def test_operator_double_satisfies_port_and_records() -> None:
    operator = OperatorDouble([True])
    assert isinstance(operator, OperatorPort)
    operator.notify("aviso fila 1, id ******0001")
    assert operator.confirm_continue("¿Continuar?") is True
    assert operator.confirm_continue("¿Continuar?") is False  # sin terminal
    assert operator.notifications == ["aviso fila 1, id ******0001"]
    assert len(operator.confirm_prompts) == 2


def test_operator_double_detects_leaked_identification() -> None:
    operator = OperatorDouble()
    operator.notify("id ******0001")
    operator.assert_no_full_identification(ID_1)
    operator.notify(f"id {ID_1}")
    assert operator.messages_containing(ID_1) == [f"id {ID_1}"]
    with pytest.raises(AssertionError):
        operator.assert_no_full_identification(ID_1)


def test_repeated_exception_is_fresh_each_call() -> None:
    source = FakeSource({ID_1: PortalUnavailable})
    caught: list[BaseException] = []
    for _ in range(3):
        with pytest.raises(PortalUnavailable) as info:
            source.query(_ident())
        caught.append(info.value)
    assert len({id(exc) for exc in caught}) == 3
    # El traceback no se acumula entre llamadas: cada excepción tiene el suyo, del mismo largo.
    lengths = {_traceback_length(exc) for exc in caught}
    assert len(lengths) == 1
    assert all(exc.__context__ is None for exc in caught)


def _traceback_length(exc: BaseException) -> int:
    count, tb = 0, exc.__traceback__
    while tb is not None:
        count, tb = count + 1, tb.tb_next
    return count


def test_factory_with_arguments_is_accepted() -> None:
    def factory() -> InvalidIdentification:
        return InvalidIdentification(InvalidReason.EMPTY)

    with pytest.raises(InvalidIdentification):
        FakeSource({ID_1: factory}).query(_ident())


def test_exception_instances_are_rejected() -> None:
    with pytest.raises(TypeError, match="fábrica"):
        FakeSource({ID_1: PortalUnavailable()})  # type: ignore[dict-item]  # prueba del rechazo
    with pytest.raises(TypeError, match="fábrica"):
        FakeSource(default=PortalUnavailable())  # type: ignore[arg-type]  # prueba del rechazo


def test_default_result_is_marked_as_test_data() -> None:
    assert DEFAULT_RESULT.observation == "Resultado ficticio de pruebas; no válido"


def test_same_identification_with_and_without_dv_counts_together() -> None:
    source = FakeSource()
    source.query(IdentificationInput(identification=ID_1))
    source.query(IdentificationInput(identification=ID_1, dv="7"))
    assert source.calls_for(ID_1) == 2


def test_kind_and_paced_are_read_only_properties() -> None:
    source = FakeSource()
    with pytest.raises(AttributeError):
        source.paced = True  # type: ignore[misc]  # prueba de solo lectura
    with pytest.raises(AttributeError):
        source.kind = SourceKind.SIN_CONSULTA  # type: ignore[misc]  # prueba de solo lectura


def test_operator_double_keeps_chronological_events() -> None:
    operator = OperatorDouble([True])
    operator.notify("a")
    operator.confirm_continue("b")
    operator.notify("c")
    assert operator.events == [("notify", "a"), ("confirm", "b"), ("notify", "c")]
    assert operator.notifications == ["a", "c"]
    assert operator.confirm_prompts == ["b"]
    assert operator.all_messages == ["a", "b", "c"]

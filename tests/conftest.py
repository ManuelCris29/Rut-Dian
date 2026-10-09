"""Configuración global de pytest.

Guard de red (Obs-6, ADR-0003): ninguna prueba que no esté marcada ``portal_real`` puede abrir
conexiones salientes a hosts distintos de localhost / 127.0.0.1 / ::1.

Diseño:
- Se instala en ``pytest_configure`` (antes de la recolección, de los imports de prueba y de las
  fixtures de sesión/módulo) y se retira en ``pytest_unconfigure``.
- Un indicador global se apaga solo mientras corre una prueba marcada ``portal_real``.
- Cubre ``socket.socket.connect``, ``connect_ex``, ``sendto`` (UDP), ``socket.create_connection``
  y asyncio (``BaseEventLoop.create_connection``/``sock_connect`` y la variante Proactor de Windows,
  que usa ConnectEx y no pasa por ``socket.connect``).
- Se evaluó ``pytest-socket``: no está en Context7 (API no verificable) y tampoco cubre el
  ProactorEventLoop de Windows; se mantiene este guard propio y sin dependencia nueva.

Límites conocidos (no cubiertos):
- Procesos hijos, p. ej. el driver Node de Playwright: el control allí es ``context.route`` en T-38.
- ``_socket.socket`` crudo (tipo C inmutable) y resolución DNS (``getaddrinfo``).
"""

import asyncio
import asyncio.base_events
import asyncio.proactor_events as proactor_events
import os
import socket
from collections.abc import Callable, Iterator
from typing import Any, NoReturn

import pytest

from rut_checker.infra.settings import Settings

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Estado del guard: se desactiva solo durante pruebas ``portal_real``.
_state = {"enabled": True}
_patches: list[tuple[object, str, object]] = []


def _is_local(address: object) -> bool:
    """Indica si la dirección de socket apunta a la máquina local."""
    if isinstance(address, str | bytes):  # AF_UNIX: ruta de archivo, no sale a la red
        return True
    if isinstance(address, tuple) and address:
        host = address[0]
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        return isinstance(host, str) and host in LOCAL_HOSTS
    return False


def _block(address: object) -> NoReturn:
    pytest.fail(
        f"red saliente bloqueada por el guard de pruebas (host={address!r}); "
        "solo se permite localhost. Las pruebas reales deben marcarse portal_real.",
        pytrace=False,
    )


def _check(address: object) -> None:
    if _state["enabled"] and not _is_local(address):
        _block(address)


def _patch(owner: object, name: str, replacement: object) -> None:
    _patches.append((owner, name, getattr(owner, name)))
    setattr(owner, name, replacement)


def _wrap_socket_method(name: str, address_index: int) -> None:
    # Any: firma genérica de métodos de socket; se reenvían tal cual al original.
    original: Callable[..., Any] = getattr(socket.socket, name)

    def guarded(self: socket.socket, *args: Any, **kwargs: Any) -> Any:
        _check(args[address_index] if args else None)
        return original(self, *args, **kwargs)

    _patch(socket.socket, name, guarded)


def _wrap_loop_host_port(owner: type, name: str) -> None:
    """Envuelve ``create_connection(protocol_factory, host, port, ...)`` de un event loop."""
    original: Callable[..., Any] = getattr(owner, name)

    def guarded(self: object, *args: Any, **kwargs: Any) -> Any:
        host = kwargs.get("host", args[1] if len(args) > 1 else None)
        port = kwargs.get("port", args[2] if len(args) > 2 else None)
        if host is not None:
            _check((host, port))
        return original(self, *args, **kwargs)

    _patch(owner, name, guarded)


def _wrap_loop_sock_connect(owner: type) -> None:
    """Envuelve ``sock_connect(sock, address)`` (selector y Proactor)."""
    name = "sock_connect"
    original: Callable[..., Any] = getattr(owner, name)

    def guarded(self: object, sock: object, address: object) -> Any:
        _check(address)
        return original(self, sock, address)

    _patch(owner, name, guarded)


def _install_guard() -> None:
    _wrap_socket_method("connect", 0)
    _wrap_socket_method("connect_ex", 0)
    _wrap_socket_method("sendto", -1)  # UDP: la dirección es el último argumento posicional

    original_create = socket.create_connection

    def guarded_create(address: tuple[str, int], *args: Any, **kwargs: Any) -> socket.socket:
        _check(address)
        return original_create(address, *args, **kwargs)

    _patch(socket, "create_connection", guarded_create)

    _wrap_loop_host_port(asyncio.base_events.BaseEventLoop, "create_connection")
    _wrap_loop_sock_connect(asyncio.base_events.BaseEventLoop)
    _wrap_loop_sock_connect(proactor_events.BaseProactorEventLoop)


def pytest_configure(config: pytest.Config) -> None:
    _install_guard()


def pytest_unconfigure(config: pytest.Config) -> None:
    while _patches:
        owner, name, original = _patches.pop()
        setattr(owner, name, original)


@pytest.fixture(autouse=True)
def _network_guard_scope(request: pytest.FixtureRequest) -> Iterator[None]:
    """Exime del guard solo las pruebas marcadas ``portal_real`` (ejecución manual)."""
    exempt = request.node.get_closest_marker("portal_real") is not None
    if exempt:
        _state["enabled"] = False
    try:
        yield
    finally:
        _state["enabled"] = True


@pytest.fixture(autouse=True, scope="session")
def _isolate_settings_from_real_env() -> Iterator[None]:
    """Ninguna prueba lee el `.env` real ni variables `RUT_*` heredadas del entorno.

    Se desactiva `env_file` en la configuración de `Settings` (así un `Settings()` sin
    argumentos tampoco toca el `.env` del repositorio) y se limpian las variables `RUT_*`.
    Las pruebas que necesiten valores usan `monkeypatch.setenv`.
    """
    previous = Settings.model_config.get("env_file")
    Settings.model_config["env_file"] = None
    with pytest.MonkeyPatch.context() as patch:
        for name in list(os.environ):
            if name.upper().startswith("RUT_"):
                patch.delenv(name)
        yield
    Settings.model_config["env_file"] = previous

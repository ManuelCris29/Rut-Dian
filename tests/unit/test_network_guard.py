"""Pruebas del guard de red definido en ``tests/conftest.py`` (Obs-6)."""

import asyncio
import socket
from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
BLOCKED = pytest.fail.Exception
MESSAGE = "red saliente bloqueada"


def test_outbound_socket_to_non_localhost_fails() -> None:
    """Una conexión saliente a un host no local falla antes de salir a la red."""
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(BLOCKED, match=MESSAGE),
    ):
        sock.connect(("192.0.2.1", 80))


def test_connect_ex_to_non_localhost_fails() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(BLOCKED, match=MESSAGE),
    ):
        sock.connect_ex(("192.0.2.1", 80))


def test_ipv6_non_local_fails() -> None:
    with (
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock,
        pytest.raises(BLOCKED, match=MESSAGE),
    ):
        sock.connect(("2001:db8::1", 80, 0, 0))


def test_udp_sendto_non_local_fails() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock,
        pytest.raises(BLOCKED, match=MESSAGE),
    ):
        sock.sendto(b"x", ("192.0.2.1", 53))


def test_create_connection_to_non_localhost_fails() -> None:
    with pytest.raises(BLOCKED, match=MESSAGE):
        socket.create_connection(("portal.invalid", 443), timeout=1)


def test_asyncio_open_connection_to_non_localhost_fails() -> None:
    with pytest.raises(BLOCKED, match=MESSAGE):
        asyncio.run(asyncio.open_connection("192.0.2.1", 80))


def test_asyncio_sock_connect_to_non_localhost_fails() -> None:
    async def attempt() -> None:
        loop = asyncio.get_running_loop()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setblocking(False)
            await loop.sock_connect(sock, ("192.0.2.1", 80))

    with pytest.raises(BLOCKED, match=MESSAGE):
        asyncio.run(attempt())


def test_connection_to_localhost_is_allowed() -> None:
    """Las conexiones a 127.0.0.1 (servidor HTTP local de pruebas) siguen funcionando."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            assert client.getpeername()[0] == "127.0.0.1"


def test_asyncio_localhost_is_allowed() -> None:
    async def attempt() -> None:
        async def handle(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
        server.close()

    asyncio.run(attempt())


def test_portal_real_marker_exempts_guard(pytester: pytest.Pytester) -> None:
    """Con ``portal_real`` el guard se apaga; sin él, está activo (subproceso aislado)."""
    pytester.makeconftest(CONFTEST.read_text(encoding="utf-8"))
    pytester.makeini("[pytest]\nmarkers =\n    portal_real: manual\n")
    pytester.makepyfile(
        """
        import conftest
        import pytest

        @pytest.mark.portal_real
        def test_exempt():
            assert conftest._state["enabled"] is False

        def test_guarded():
            assert conftest._state["enabled"] is True
        """
    )
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=2)

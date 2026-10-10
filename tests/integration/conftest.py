"""Fixtures de integración del adaptador del portal (T-38).

Todo corre contra un servidor HTTP local (127.0.0.1) con fixtures SINTÉTICOS: nunca la DIAN.

- Navegador: Chromium en modo ``headless=True`` SOLO aquí, porque son pruebas de mecanismo sobre
  fixtures locales sin personas delante (CI). En producción el adaptador fija ``headless=False``
  en código (ADR-0003 §3; lo implementa T-49).
- Guard de red del navegador: el guard de ``tests/conftest.py`` solo cubre sockets del proceso de
  Python, no al driver de Playwright; por eso cada contexto registra ``context.route`` y aborta
  toda petición que no sea local (localhost, 127.0.0.1, ::1, ``about:``, ``data:``, ``file:``).
- No se usa ``pytest-playwright``: estas fixtures dan control explícito del guard antes de la
  primera navegación y evitan un plugin más con su propia gestión de contextos.
"""

import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Request,
    Route,
    WebSocketRoute,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError
from portal_support import SELECTORS_FILE, SYNTHETIC_DIR, BrowserGuard

from rut_checker.adapters.dian_portal.selectors import (
    EnabledPortal,
    enabled_portal_from_synthetic_fixture,
)

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})
LOCAL_SCHEMES = frozenset({"about", "data", "file", "blob"})
MAINTENANCE_IMAGE = "Mantenimiento-Consulta-RUT.jpg"
# GIF 1x1 mínimo: contenido de la "imagen de mantenimiento" local.
TINY_GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)


def is_local_url(url: str) -> bool:
    """Indica si la URL es local (única permitida en el navegador de pruebas)."""
    parts = urlsplit(url)
    if parts.scheme in LOCAL_SCHEMES:
        return True
    return parts.scheme in {"http", "https", "ws", "wss"} and parts.hostname in LOCAL_HOSTS


class _Handler(BaseHTTPRequestHandler):
    """Sirve los fixtures sintéticos y simula respuestas de error/redirección."""

    def log_message(self, format: str, *args: object) -> None:
        """Silencia el registro del servidor de pruebas."""

    def _send(self, status: int, body: bytes, content_type: str, location: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/redirige-a-mantenimiento":
            self._send(302, b"", "text/plain", location=f"/img/{MAINTENANCE_IMAGE}")
        elif path == f"/img/{MAINTENANCE_IMAGE}":
            self._send(200, TINY_GIF, "image/gif")
        elif path == "/redirige-a-otra-ruta":
            self._send(302, b"", "text/plain", location="/html/mecanismo_formulario.html")
        elif path.startswith("/estado/"):
            raw = path.rsplit("/", 1)[1]
            code = int(raw) if raw.isdecimal() and len(raw) == 3 else 400
            self._send(code, b"<html><body><p>respuesta sintetica</p></body></html>", "text/html")
        elif path.startswith("/html/"):
            file = SYNTHETIC_DIR / Path(path).name
            if file.is_file():
                self._send(200, file.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, b"", "text/plain")
        else:
            self._send(404, b"", "text/plain")


@pytest.fixture(scope="session")
def local_server() -> Iterator[str]:
    """Servidor HTTP local en un puerto libre de 127.0.0.1; devuelve la URL base."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    """Chromium headless solo para pruebas de mecanismo sobre fixtures locales.

    Ámbito de módulo (no de sesión): la API síncrona de Playwright deja un event loop en marcha en
    el hilo principal mientras vive, lo que rompería ``asyncio.run`` en las pruebas unitarias.

    Solo en pruebas: ``--host-resolver-rules`` hace que todo nombre de host salvo 127.0.0.1 y
    localhost falle al resolver, como segunda barrera tras ``context.route``. El adaptador de
    producción NO usa ``args`` (lo verifica ``test_architecture``).
    """
    with sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch(
                headless=True,
                args=[
                    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"
                ],
            )
        except PlaywrightError:
            pytest.fail("Chromium no disponible. Ejecute: uv run playwright install chromium")
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def browser_guard() -> BrowserGuard:
    return BrowserGuard()


@pytest.fixture
def context(browser: Browser, browser_guard: BrowserGuard) -> Iterator[BrowserContext]:
    """Contexto nuevo por prueba con el guard de red del navegador ya registrado."""
    ctx = browser.new_context(service_workers="block")

    def guard(route: Route) -> None:
        url = route.request.url
        if is_local_url(url):
            route.continue_()
        else:
            browser_guard.blocked.append(urlsplit(url).scheme)
            route.abort()

    def guard_websocket(ws: WebSocketRoute) -> None:
        if is_local_url(ws.url):
            ws.connect_to_server()
        else:
            # Sin `connect_to_server()` el WebSocket queda simulado en el navegador: no sale a la
            # red. (`ws.close()` bloquea dentro del manejador con la API síncrona.)
            browser_guard.blocked_websockets.append(urlsplit(ws.url).scheme)

    def record_leak(request: Request) -> None:
        if not is_local_url(request.url):
            browser_guard.leaked.append(urlsplit(request.url).scheme)

    ctx.route("**/*", guard)
    ctx.route_web_socket("**/*", guard_websocket)
    ctx.on("requestfinished", record_leak)  # una petición no local que termina es una fuga
    try:
        yield ctx
    finally:
        ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    return context.new_page()


@pytest.fixture(scope="session")
def enabled_portal() -> EnabledPortal:
    """Selectores sintéticos de ``tests/fixtures/selectors_test.yaml`` (nunca los reales)."""
    return enabled_portal_from_synthetic_fixture(SELECTORS_FILE)


@pytest.fixture
def fixture_url(local_server: str) -> Callable[[str], str]:
    """URL local de un fixture sintético por nombre de archivo."""
    return lambda name: f"{local_server}/html/{name}"

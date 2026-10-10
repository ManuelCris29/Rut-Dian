"""Constantes y utilidades compartidas por las pruebas del adaptador del portal (T-38, T-49)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, Request, Route, WebSocketRoute

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_DIR = ROOT / "tests" / "fixtures" / "html" / "sintetico"
SELECTORS_FILE = ROOT / "tests" / "fixtures" / "selectors_test.yaml"
UrlOf = Callable[[str], str]
SYNTHETIC_HEADER = "SINTÉTICO — no representa el portal de la DIAN"
WAIT_MS = 5000
SHORT_MS = 300
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})
LOCAL_SCHEMES = frozenset({"about", "data", "file", "blob"})
# Solo en pruebas: todo nombre de host salvo 127.0.0.1 y localhost falla al resolver, como segunda
# barrera tras el guard de contexto. El adaptador de producción NO usa `args`.
HOST_RESOLVER_ARGS = ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"]


@dataclass
class BrowserGuard:
    """Registro de peticiones del navegador abortadas por no ser locales."""

    blocked: list[str] = field(default_factory=list)
    blocked_websockets: list[str] = field(default_factory=list)
    leaked: list[str] = field(default_factory=list)


def is_local_url(url: str) -> bool:
    """Indica si la URL es local (única permitida en el navegador de pruebas)."""
    parts = urlsplit(url)
    if parts.scheme in LOCAL_SCHEMES:
        return True
    return parts.scheme in {"http", "https", "ws", "wss"} and parts.hostname in LOCAL_HOSTS


def install_browser_guard(ctx: BrowserContext, guard: BrowserGuard) -> None:
    """Registra en `ctx` el guard de red: aborta lo no local y anota cada intento."""

    def guard_route(route: Route) -> None:
        url = route.request.url
        if is_local_url(url):
            route.continue_()
        else:
            guard.blocked.append(urlsplit(url).scheme)
            route.abort()

    def guard_websocket(ws: WebSocketRoute) -> None:
        if is_local_url(ws.url):
            ws.connect_to_server()
        else:
            # Sin `connect_to_server()` el WebSocket queda simulado en el navegador: no sale a la
            # red. (`ws.close()` bloquea dentro del manejador con la API síncrona.)
            guard.blocked_websockets.append(urlsplit(ws.url).scheme)

    def record_leak(request: Request) -> None:
        if not is_local_url(request.url):
            guard.leaked.append(urlsplit(request.url).scheme)

    ctx.route("**/*", guard_route)
    ctx.route_web_socket("**/*", guard_websocket)
    ctx.on("requestfinished", record_leak)  # una petición no local que termina es una fuga

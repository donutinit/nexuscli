import json
import re
import time
from pathlib import Path

import httpx
import pytest

from nexuscli import config
from nexuscli.client import Client, Sesion
from nexuscli.nexus import Nexus, Tarea
from nexuscli.pace import Pacer


class FakeNexus:
    """Servidor falso: responde por endpoint y guarda cada petición."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[str, object] = {}

    def on(self, endpoint: str, response) -> None:
        self.routes[endpoint] = response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        url = str(request.url)
        for endpoint, resp in self.routes.items():
            if url.endswith(endpoint) or endpoint in url:
                if callable(resp):
                    resp = resp(request)
                if isinstance(resp, httpx.Response):
                    return resp
                if isinstance(resp, str):
                    return httpx.Response(200, text=resp)
                return httpx.Response(200, json=resp)
        return httpx.Response(404, text=f"sin ruta para {url}")

    def calls(self, endpoint: str) -> list[httpx.Request]:
        return [r for r in self.requests if str(r.url).endswith(endpoint)]


def multipart_fields(request: httpx.Request) -> list[tuple[str, str]]:
    body = request.content.decode("latin-1")
    return re.findall(r'name="([^"]+)"(?:; filename="[^"]*")?\r\n(?:Content-Type: [^\r]+\r\n)?\r\n(.*?)\r\n--', body, re.S)


def json_body(request: httpx.Request) -> dict:
    return json.loads(request.content)


@pytest.fixture
def fake():
    return FakeNexus()


@pytest.fixture
def client(fake, tmp_path):
    http = httpx.Client(transport=httpx.MockTransport(fake))
    c = Client(pacer=Pacer("off"), state=tmp_path, http=http,
               credenciales=config.Credenciales("1234567", "secreta", "test"))
    c._sesion = Sesion(token="TOK", area_id=56, rol_id=5, cuenta_id=100200, creada=time.time(), expira=time.time() + 3600)
    return c


@pytest.fixture
def nx(client, tmp_path):
    from nexuscli.materias import Materias
    return Nexus(client, materias=Materias(tmp_path / "materias"))


@pytest.fixture
def tarea_equipo():
    return Tarea(curso_id=100002, curso="Guion cinematográfico | AGO26 | 202", tipo=1, id=5000047,
                 clave="3.2", nombre="Resumen", valor=5.0, inicio=None, fin=None, limite=None,
                 en_equipo=True, equipo_id=90006)


@pytest.fixture
def archivo(tmp_path) -> Path:
    p = tmp_path / "Resumen_equipo6.pdf"
    p.write_bytes(b"%PDF-1.4 prueba")
    return p

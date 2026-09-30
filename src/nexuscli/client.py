"""Cliente HTTP de Nexus: login por SIASE, sesión persistente, llamadas y archivos.

Nexus es un Angular que habla con `api.nexus.uanl.mx/WebApi/<Dominio>/<Método>` por POST
con JSON. La autenticación son headers (Token, AreaAcademicaId, RolId, SistemaId); el
token sale de `Seguridad/CrearSesionSIASE`, que recibe el parámetro `Ctrl` que SIASE pone
en la liga "Ingresar" a Nexus. Todo eso se puede hacer sin navegador.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import httpx

from . import config
from .pace import Pacer

TOKEN_EXPIRADO = 2004
# 2011 = "La sesión no existe": Nexus admite una sola sesión por usuario, así que entrar desde
# otro lado (el navegador, nexus-watcher u otro estado de nexuscli) invalida este token.
SESION_INVALIDA = {TOKEN_EXPIRADO, 2011}


class NexusError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, endpoint: str | None = None):
        super().__init__(message)
        self.code = code
        self.endpoint = endpoint

    def __str__(self) -> str:
        base = super().__str__()
        if self.code is not None:
            base = f"{base} (código {self.code})"
        if self.endpoint:
            base = f"{self.endpoint}: {base}"
        return base


class LoginError(NexusError):
    pass


@dataclass
class Sesion:
    token: str
    area_id: int
    rol_id: int
    cuenta_id: int = 0
    persona_id: int = 0
    nombre: str = ""
    matricula: str = ""
    correo: str = ""
    creada: float = 0.0
    expira: float = 0.0

    @property
    def vigente(self) -> bool:
        return bool(self.token) and time.time() < self.expira


class Client:
    def __init__(
        self,
        pacer: Pacer | None = None,
        state: Path | None = None,
        http: httpx.Client | None = None,
        credenciales: config.Credenciales | None = None,
        verbose: bool = False,
    ) -> None:
        self.pacer = pacer or Pacer("normal")
        self.state = state or config.state_dir()
        self.http = http or httpx.Client(
            timeout=httpx.Timeout(30.0, read=180.0, write=600.0),
            follow_redirects=True,
            headers={"User-Agent": config.USER_AGENT, "Accept-Language": "es-MX,es;q=0.9,en;q=0.5"},
        )
        self._credenciales = credenciales
        self._sesion: Sesion | None = None
        self.verbose = verbose
        self.llamadas = 0

    # ------------------------------------------------------------------ sesión

    @property
    def sesion_path(self) -> Path:
        return self.state / "sesion.json"

    def cargar_sesion(self) -> Sesion | None:
        try:
            data = json.loads(self.sesion_path.read_text(encoding="utf-8"))
            return Sesion(**data)
        except (FileNotFoundError, ValueError, TypeError):
            return None

    def guardar_sesion(self, s: Sesion) -> None:
        config.ensure_private_dir(self.state)
        tmp = self.sesion_path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(s), fh)
        tmp.replace(self.sesion_path)

    def olvidar_sesion(self) -> None:
        self._sesion = None
        self.sesion_path.unlink(missing_ok=True)

    def sesion(self) -> Sesion:
        if self._sesion and self._sesion.vigente:
            return self._sesion
        s = self.cargar_sesion()
        if s and s.vigente:
            self._sesion = s
            return s
        return self.login()

    def credenciales(self) -> config.Credenciales:
        if self._credenciales is None:
            self._credenciales = config.load_credentials()
        return self._credenciales

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"· {msg}", flush=True)

    def entrar_siase(self) -> str:
        """Login en SIASE. Regresa la página de carreras (eselcarrera.htm), que trae la sesión de
        SIASE (HTMLtrim) y la liga con la que SIASE abre Nexus."""
        cred = self.credenciales()
        self._log("login en SIASE")
        self.pacer.antes()
        r = self.http.get(config.SIASE_LOGIN)
        self.pacer.despues()
        r.raise_for_status()
        html = r.content.decode("latin-1")
        form = dict(re.findall(r'<input[^>]*type="hidden"[^>]*name="(\w+)"[^>]*value="([^"]*)"', html, re.I))
        form.update({"HTMLTipCve": "01", "HTMLUsuCve": cred.usuario, "HTMLPassword": cred.password})

        self.pacer.teclear()
        self.pacer.antes()
        r = self.http.post(config.SIASE_POST, data=form, headers={"Referer": config.SIASE_LOGIN})
        self.pacer.despues()
        r.raise_for_status()
        return r.content.decode("latin-1")

    def login(self) -> Sesion:
        cred = self.credenciales()
        html = self.entrar_siase()
        m = re.search(r'plataformanexus\.uanl\.mx/#/LoginSIASE\?([^"\']+)', html)
        if not m:
            raise LoginError(_motivo_login(html))
        params = dict(p.split("=", 1) for p in m.group(1).split("&") if "=" in p)
        ctrl = unquote(params.get("Ctrl", "")).replace(" ", "+")
        if not ctrl:
            raise LoginError("SIASE no devolvió el parámetro Ctrl para Nexus")

        self._log("creando sesión de Nexus")
        headers = {
            "Control": ctrl,
            "ClienteIp": "0.0.0.0",
            "Usuario": params.get("Usu", ""),
            "UsuarioClave": params.get("HTMLUsuario", cred.usuario),
            "TipoClave": params.get("HTMLTipCve", "01"),
        }
        j = self._post("Seguridad/CrearSesionSIASE", {}, extra=headers, auth=False)
        ses = j.get("Sesion") or {}
        if not ses.get("Token"):
            raise LoginError("Nexus no devolvió token de sesión")
        s = Sesion(
            token=ses["Token"],
            area_id=int(ses.get("AreaAcademicaId") or 0),
            rol_id=int(ses.get("RolId") or 0),
            creada=time.time(),
        )
        s.expira = _expira(ses, s.creada)
        self._sesion = s

        perfil = self.call("Seguridad/ConsultarPerfil", {})
        persona = perfil.get("Persona") or {}
        cuenta = (persona.get("Cuentas") or [{}])[0]
        s.persona_id = int(persona.get("PersonaId") or 0)
        s.cuenta_id = int(cuenta.get("CuentaId") or 0)
        s.matricula = cuenta.get("NombreUsuario") or cred.usuario
        s.correo = cuenta.get("CorreoUniversitario") or ""
        s.nombre = " ".join(
            x for x in (persona.get("Nombre"), persona.get("ApellidoPaterno"), persona.get("ApellidoMaterno")) if x
        )
        self.guardar_sesion(s)
        return s

    # ------------------------------------------------------------------ llamadas

    def _auth_headers(self) -> dict[str, str]:
        s = self._sesion or self.sesion()
        return {"Token": s.token, "AreaAcademicaId": str(s.area_id), "RolId": str(s.rol_id)}

    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Origin": config.WEB,
            "Referer": config.WEB + "/",
            "SistemaId": "1",
        }

    def _post(
        self,
        endpoint: str,
        body: Any,
        *,
        extra: dict[str, str] | None = None,
        auth: bool = True,
        peso: float = 1.0,
        files: list[tuple[str, Any]] | None = None,
    ) -> dict:
        headers = self._base_headers()
        if auth:
            headers.update(self._auth_headers())
        if extra:
            headers.update(extra)
        self.pacer.antes(peso)
        self._log(f"POST {endpoint}")
        try:
            if files is not None:
                r = self.http.post(config.API + endpoint, files=files, headers=headers)
            else:
                headers["Content-Type"] = "application/json"
                r = self.http.post(config.API + endpoint, content=json.dumps(body), headers=headers)
        except httpx.HTTPError as e:
            raise NexusError(f"error de red: {e}", endpoint=endpoint) from e
        finally:
            self.pacer.despues()
            self.llamadas += 1
        if r.status_code == 401:
            raise NexusError("sesión rechazada", code=TOKEN_EXPIRADO, endpoint=endpoint)
        if r.status_code >= 400:
            raise NexusError(f"HTTP {r.status_code}: {r.text[:200]}", endpoint=endpoint)
        try:
            j = r.json()
        except ValueError as e:
            raise NexusError(f"respuesta no es JSON: {r.text[:200]!r}", endpoint=endpoint) from e
        if isinstance(j, dict) and "Code" in j:
            raise NexusError(j.get("Message") or "error de Nexus", code=j.get("Code"), endpoint=endpoint)
        if isinstance(j, dict) and auth and self._sesion and isinstance(j.get("Sesion"), dict):
            self._sesion.expira = _expira(j["Sesion"], time.time())
        return j

    def call(self, endpoint: str, body: Any = None, *, peso: float = 1.0) -> dict:
        """POST a WebApi/<endpoint>. Si el token expiró, vuelve a entrar una vez."""
        body = {} if body is None else body
        self.sesion()
        try:
            j = self._post(endpoint, body, peso=peso)
        except NexusError as e:
            if e.code not in SESION_INVALIDA:
                raise
            self._log("la sesión ya no vale (expiró o se entró desde otro lado): login de nuevo")
            self.olvidar_sesion()
            self.login()
            j = self._post(endpoint, body, peso=peso)
        if self._sesion:
            self.guardar_sesion(self._sesion)
        return j

    def upload(self, endpoint: str, campos: list[tuple[str, Any]], *, documento_id: int = 0, peso: float = 2.0) -> dict:
        """multipart/form-data como lo manda el Angular (REQUEST_UPLOAD)."""
        self.sesion()
        extra = {"DocumentoId": str(documento_id)}
        try:
            return self._post(endpoint, None, extra=extra, files=campos, peso=peso)
        except NexusError as e:
            if e.code not in SESION_INVALIDA:
                raise
            self.olvidar_sesion()
            self.login()
            _rebobinar(campos)
            return self._post(endpoint, None, extra=extra, files=campos, peso=peso)

    def descargar(self, url_relativa: str, destino: Path) -> Path:
        """Documentos de Nexus: https://plataformanexus.uanl.mx/<Documento.URL>."""
        url = config.WEB + "/" + quote(url_relativa.lstrip("/"), safe="/")
        destino.parent.mkdir(parents=True, exist_ok=True)
        self.pacer.antes()
        self._log(f"GET {url}")
        tmp = destino.with_name(destino.name + ".parcial")
        try:
            with self.http.stream("GET", url, headers={"Referer": config.WEB + "/"}) as r:
                if r.status_code >= 400:
                    raise NexusError(f"HTTP {r.status_code} al bajar {url_relativa}")
                with tmp.open("wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
        finally:
            self.pacer.despues()
        tmp.replace(destino)
        return destino


def campo_archivo(nombre: str, path: Path) -> tuple[str, Any]:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return (nombre, (path.name, path.open("rb"), mime))


def campo(nombre: str, valor: Any) -> tuple[str, Any]:
    """Campo de texto en multipart; replica FormData.append(nombre, String(valor))."""
    if valor is True:
        valor = "true"
    elif valor is False:
        valor = "false"
    elif valor is None:
        valor = "null"
    return (nombre, (None, str(valor)))


def _rebobinar(campos: list[tuple[str, Any]]) -> None:
    for _, v in campos:
        if isinstance(v, tuple) and len(v) >= 2 and hasattr(v[1], "seek"):
            v[1].seek(0)


def _expira(ses: dict, ahora: float) -> float:
    restante = (ses.get("Tiempo") or {}).get("Restante") or 0
    try:
        restante = float(restante)
    except (TypeError, ValueError):
        restante = 0
    # Margen de 5 min; si Nexus no dice, asumimos una hora.
    return ahora + (restante - 300 if restante > 600 else 3600)


def _motivo_login(html: str) -> str:
    texto = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    m = re.search(r"[^.]{0,80}(incorrect|inv[aá]lid|no existe|bloquead|contrase|intente)[^.]{0,120}", texto, re.I)
    if m:
        return "SIASE rechazó el login: " + m.group(0).strip()
    return "SIASE no devolvió la liga a Nexus (¿matrícula o contraseña incorrectas?)"

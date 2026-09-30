"""Rutas, credenciales y constantes del portal."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

SIASE_LOGIN = "https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/login.htm"
SIASE_POST = "https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/eselcarrera.htm"
WEB = "https://plataformanexus.uanl.mx"
API = "https://api.nexus.uanl.mx/WebApi/"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
TZ = "America/Monterrey"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "nexuscli"


def state_dir() -> Path:
    if os.environ.get("NEXUS_STATE_DIR"):
        return Path(os.environ["NEXUS_STATE_DIR"])
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "nexuscli"


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def escribir_privado(path: Path, contenido: str) -> None:
    """Escribe de forma atómica con permisos 600, dentro de una carpeta 700."""
    ensure_private_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(contenido)
    os.replace(tmp, path)


def credentials_path() -> Path:
    if os.environ.get("NEXUS_CREDENCIALES"):
        return Path(os.environ["NEXUS_CREDENCIALES"]).expanduser()
    return config_dir() / "credenciales"


@dataclass(frozen=True)
class Credenciales:
    usuario: str
    password: str
    origen: str


class CredencialesError(RuntimeError):
    pass


# Llaves aceptadas en el archivo, en orden de preferencia. USER/PASS y PORTAL_* son los
# nombres que ya usaban nexus.env y nexus-watcher.
_USER_KEYS = ("NEXUS_USUARIO", "PORTAL_USERNAME", "USER")
_PASS_KEYS = ("NEXUS_PASSWORD", "PORTAL_PASSWORD", "PASS")


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def load_credentials() -> Credenciales:
    # Variables de entorno explícitas (nunca $USER, que es el usuario de la máquina).
    env_user = os.environ.get("NEXUS_USUARIO")
    env_pass = os.environ.get("NEXUS_PASSWORD")
    if env_user and env_pass:
        return Credenciales(env_user, env_pass, "entorno (NEXUS_USUARIO/NEXUS_PASSWORD)")

    path = credentials_path()
    if not path.exists():
        raise CredencialesError(
            f"No encuentro credenciales en {path}.\n"
            "Crea el archivo (permisos 600) con:\n"
            "  NEXUS_USUARIO=<matrícula>\n"
            "  NEXUS_PASSWORD=<contraseña de SIASE>"
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise CredencialesError(f"{path} tiene permisos {oct(mode)}; corre: chmod 600 {path}")
    values = _parse_env(path.read_text(encoding="utf-8"))
    user = next((values[k] for k in _USER_KEYS if values.get(k)), "")
    password = next((values[k] for k in _PASS_KEYS if values.get(k)), "")
    if not user or not password:
        raise CredencialesError(f"{path} no tiene NEXUS_USUARIO y NEXUS_PASSWORD")
    return Credenciales(user, password, str(path))

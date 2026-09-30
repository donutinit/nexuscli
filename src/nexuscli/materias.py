"""Códigos cortos por materia, registro de clones y avisos de cierre de semestre.

- `~/.config/nexuscli/materias`: una línea por materia, `<CursoId> <código>  # nombre`. Lo
  edita `nexuscli codigo` y también se puede editar a mano. El código sirve en `-c` y es el
  nombre de carpeta por defecto de `clonar` (por ejemplo anau, crng).
- `~/.local/state/nexuscli/clones.json`: dónde se ha clonado cada materia y cuándo.

Nexus deja de listar una materia poco después de que termina (ni siquiera sale en el historial),
así que lo que no se clonó antes se pierde. De ahí los avisos de cierre.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import config, texto

VENTANA_CIERRE_DIAS = 21
CLON_VIEJO_DIAS = 7
_CODIGO = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
_VACIAS = {"y", "e", "de", "del", "la", "las", "el", "los", "en", "a", "para", "con", "por", "al", "o", "u", "i", "ii", "iii"}


class CodigoError(ValueError):
    pass


def materias_path() -> Path:
    return config.config_dir() / "materias"


def proponer(nombre: str, usados: set[str] | None = None) -> str:
    """Código de 4 letras: dos del primer nombre y dos (o una y una) de los siguientes: 'Análisis audiovisual' -> anau,
    'Creación narrativa y guionismo' -> crng, 'Antropología visual' -> anvi."""
    usados = usados or set()
    palabras = [p for p in re.findall(r"[a-z0-9]+", texto.normalizar(texto.curso_corto(nombre))) if p not in _VACIAS]
    if not palabras:
        base = "curso"
    elif len(palabras) == 1:
        base = palabras[0][:4]
    elif len(palabras) == 2:
        base = palabras[0][:2] + palabras[1][:2]
    else:
        base = palabras[0][:2] + "".join(p[0] for p in palabras[1:3])
    codigo, n = base, 2
    while codigo in usados:
        codigo = f"{base}{n}"
        n += 1
    return codigo


def validar(codigo: str) -> str:
    c = codigo.strip().lower()
    if not _CODIGO.match(c):
        raise CodigoError(f"{codigo!r} no sirve como código: usa minúsculas, números y guiones (máx. 24), p. ej. anau")
    if c.isdigit():
        raise CodigoError("un código no puede ser solo números (se confundiría con el id del curso)")
    return c


class Materias:
    """Lee y escribe ~/.config/nexuscli/materias conservando comentarios."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or materias_path()
        self.codigos: dict[int, str] = {}
        self.nombres: dict[int, str] = {}
        self._leer()

    def _leer(self) -> None:
        try:
            lineas = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return
        for ln in lineas:
            cuerpo, _, comentario = ln.partition("#")
            partes = cuerpo.split()
            if len(partes) >= 2 and partes[0].isdigit():
                cid = int(partes[0])
                self.codigos[cid] = partes[1].lower()
                self.nombres[cid] = comentario.strip()

    def codigo(self, curso_id: int) -> str | None:
        return self.codigos.get(curso_id)

    def curso_id(self, codigo: str) -> int | None:
        c = codigo.strip().lower()
        return next((cid for cid, cod in self.codigos.items() if cod == c), None)

    def asignar(self, curso_id: int, codigo: str, nombre: str) -> str:
        c = validar(codigo)
        otro = self.curso_id(c)
        if otro is not None and otro != curso_id:
            raise CodigoError(f"el código {c} ya es de {self.nombres.get(otro) or otro}; elige otro")
        self.codigos[curso_id] = c
        self.nombres[curso_id] = nombre
        self._guardar()
        return c

    def quitar(self, curso_id: int) -> bool:
        if curso_id not in self.codigos:
            return False
        del self.codigos[curso_id]
        self.nombres.pop(curso_id, None)
        self._guardar()
        return True

    def _guardar(self) -> None:
        lineas = [
            "# Códigos de materia para nexuscli: <CursoId> <código>  # nombre en Nexus",
            "# El código sirve en -c y es la carpeta por defecto de `nexuscli clonar`.",
        ]
        for cid, cod in sorted(self.codigos.items(), key=lambda x: x[1]):
            nombre = self.nombres.get(cid) or ""
            lineas.append(f"{cid} {cod}" + (f"  # {nombre}" if nombre else ""))
        config.escribir_privado(self.path, "\n".join(lineas) + "\n")


# ---------------------------------------------------------------------- clones


def clones_path(state: Path) -> Path:
    return state / "clones.json"


def leer_clones(state: Path) -> dict[str, list[dict]]:
    try:
        return json.loads(clones_path(state).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def registrar_clon(state: Path, curso_id: int, nombre: str, destino: Path) -> None:
    datos = leer_clones(state)
    lista = [c for c in datos.get(str(curso_id), []) if c.get("ruta") != str(destino.resolve())]
    lista.append({"ruta": str(destino.resolve()), "curso": nombre,
                  "sincronizado": texto.ahora().isoformat(timespec="minutes")})
    datos[str(curso_id)] = lista
    config.escribir_privado(clones_path(state), json.dumps(datos, ensure_ascii=False, indent=1) + "\n")


def ultimo_clon(state: Path, curso_id: int) -> dict | None:
    """El clon más reciente que todavía existe en disco."""
    vivos = [c for c in leer_clones(state).get(str(curso_id), []) if Path(c["ruta"]).is_dir()]
    return max(vivos, key=lambda c: c["sincronizado"]) if vivos else None


# ---------------------------------------------------------------------- avisos de cierre


@dataclass
class AvisoCierre:
    curso_id: int
    curso: str
    fin: datetime
    motivo: str      # "sin clon" | "clon viejo" | "terminó"
    texto: str
    comando: str


def avisos_de_cierre(cursos, materias: Materias, state: Path, ahora: datetime | None = None) -> list[AvisoCierre]:
    ahora = ahora or texto.ahora()
    out: list[AvisoCierre] = []
    for c in cursos:
        fin = texto.fecha(c.fin)
        if not fin:
            continue
        dias = (fin - ahora).total_seconds() / 86400
        if dias > VENTANA_CIERRE_DIAS:
            continue
        cod = materias.codigo(c.id)
        comando = f"nexuscli clonar -c {cod or c.id} -o <carpeta>" + ("" if cod else " --como <código>")
        clon = ultimo_clon(state, c.id)
        nombre = texto.curso_corto(c.nombre)
        cuando = texto.fmt_fecha(fin, con_hora=False)
        if clon:
            ultimo = texto.fecha(clon["sincronizado"])
            if ultimo and (ahora - ultimo).days < CLON_VIEJO_DIAS:
                continue
            comando = f"nexuscli clonar -c {cod or c.id} -o {Path(clon['ruta']).parent}" + (
                f" --como {Path(clon['ruta']).name}" if Path(clon["ruta"]).name != cod else "")
            motivo = "clon viejo"
            msg = (f"{nombre} termina el {cuando} y tu clon es del {texto.fmt_fecha(ultimo, con_hora=False)}; "
                   "actualízalo antes de que Nexus deje de mostrarla")
        else:
            motivo = "sin clon"
            msg = f"{nombre} termina el {cuando} y no la has clonado; después Nexus deja de mostrarla"
        if dias < 0:
            motivo = "terminó" if not clon else motivo
            msg = f"{nombre} terminó el {cuando}: Nexus puede dejar de mostrarla en cualquier momento" + (
                "" if clon else " y no la has clonado")
        out.append(AvisoCierre(c.id, c.nombre, fin, motivo, msg, comando))
    return out

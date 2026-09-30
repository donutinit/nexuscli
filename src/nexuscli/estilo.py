"""Color en la terminal, con la paleta de cuarto oscuro de donutinit.

Solo se pinta si la salida es una terminal y no hay NO_COLOR (https://no-color.org).
FORCE_COLOR=1 lo fuerza, por ejemplo para las capturas del README.
"""

from __future__ import annotations

import os
import re
import sys

_PALETA = {
    "papel": (216, 207, 192),    # #d8cfc0 texto principal
    "tenue": (125, 118, 108),    # #7d766c secundario
    "oliva": (154, 171, 136),    # #9aab88 hecho, calificada
    "rojo": (214, 96, 80),       # #d66050 vencida, error
    "naranja": (217, 135, 63),   # #d9873f pendiente, aviso
    "hueso": (202, 191, 169),    # #cabfa9 códigos de materia
    "vino": (190, 110, 125),     # #be6e7d comentarios del profe
}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def activo(stream=None) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream or sys.stdout
    return hasattr(stream, "isatty") and stream.isatty()


def pintar(texto: str, color: str | None = None, *, negrita: bool = False, tenue: bool = False,
           stream=None) -> str:
    if not texto or not activo(stream):
        return texto
    codigos = []
    if negrita:
        codigos.append("1")
    if tenue:
        codigos.append("2")
    if color:
        r, g, b = _PALETA[color]
        codigos.append(f"38;2;{r};{g};{b}")
    if not codigos:
        return texto
    return f"\x1b[{';'.join(codigos)}m{texto}\x1b[0m"


def visible(texto: str) -> str:
    return _ANSI.sub("", texto)


def ancho(texto: str) -> int:
    return len(visible(texto))

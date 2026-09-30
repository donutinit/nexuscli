"""Utilidades de texto: HTML a texto plano, fechas en español, normalización."""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from . import config

_DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def ahora() -> datetime:
    """Hora local de Monterrey, naive, igual que las fechas que devuelve Nexus."""
    return datetime.now(ZoneInfo(config.TZ)).replace(tzinfo=None)


def fecha(valor: str | None) -> datetime | None:
    if not valor or valor.startswith("0001-01-01"):
        return None
    try:
        return datetime.fromisoformat(valor[:19])
    except ValueError:
        return None


def fmt_fecha(d: datetime | None, con_hora: bool = True, anio: bool = False) -> str:
    if d is None:
        return "-"
    base = f"{_DIAS[d.weekday()]} {d.day:02d} {_MESES[d.month - 1]}"
    if anio or d.year != ahora().year:
        base += f" {d.year}"
    return f"{base} {d:%H:%M}" if con_hora else base


def relativo(d: datetime | None, ref: datetime | None = None) -> str:
    if d is None:
        return ""
    ref = ref or ahora()
    seg = (d - ref).total_seconds()
    futuro = seg >= 0
    seg = abs(seg)
    if seg < 3600:
        n, u = max(int(seg // 60), 1), "min"
    elif seg < 86400 * 2:
        n, u = int(seg // 3600), "h"
    else:
        n, u = int(seg // 86400), "d"
    return f"en {n} {u}" if futuro else f"hace {n} {u}"


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def curso_corto(nombre: str) -> str:
    """'Análisis audiovisual | AGO26 | 101' -> 'Análisis audiovisual'."""
    return (nombre or "").split("|")[0].strip()


_MINUSCULAS = {"de", "del", "la", "las", "el", "los", "y", "e", "en", "para", "por", "a", "al", "con", "o", "u"}


def titulo(s: str) -> str:
    """'FACULTAD DE ARTES VISUALES' -> 'Facultad de Artes Visuales'."""
    palabras = (s or "").lower().split()
    return " ".join(p if i and p in _MINUSCULAS else p[:1].upper() + p[1:] for i, p in enumerate(palabras))


def tamano(n: int | float | None) -> str:
    if not n:
        return "-"
    n = float(n)
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024
    return f"{n:.1f} GB"


class _Texto(HTMLParser):
    _BLOQUES = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._href: str | None = None
        self._link_txt: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self._BLOQUES and self.partes and not self.partes[-1].endswith("\n"):
            self.partes.append("\n")
        if tag == "li":
            self.partes.append("• ")
        if tag == "a":
            self._href = a.get("href")
            self._link_txt = []
        if tag == "img" and a.get("src"):
            self.partes.append(f"[imagen: {a['src']}]")

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            txt = "".join(self._link_txt).strip()
            if self._href and self._href.strip() not in txt:
                self.partes.append(f" ({self._href.strip()})")
            self._href = None
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self.partes.append("\n")

    def handle_data(self, data):
        self.partes.append(data)
        if self._href is not None:
            self._link_txt.append(data)


def html_a_texto(fragmento: str | None) -> str:
    if not fragmento:
        return ""
    p = _Texto()
    p.feed(fragmento)
    p.close()
    texto = html.unescape("".join(p.partes)).replace("\xa0", " ")
    lineas = [re.sub(r"[ \t]+", " ", ln).strip() for ln in texto.splitlines()]
    salida: list[str] = []
    for ln in lineas:
        if ln or (salida and salida[-1]):
            salida.append(ln)
    return "\n".join(salida).strip()


def recortar(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"

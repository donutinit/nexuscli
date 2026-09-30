"""Un árbol HTML tolerante para leer páginas viejas (SIASE es Progress WebSpeed de los 2000).

HTMLParser de la biblioteca estándar no arma árbol ni cierra solo lo que el navegador cierra
por su cuenta, y en SIASE abundan las celdas sin cerrar, las etiquetas en mayúsculas y los
<font> anidados. Aquí se cierran de forma implícita tr, td, th, option, li y p, como lo haría
un navegador, y hay búsquedas sencillas por etiqueta y atributos.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterator

_VACIAS = {"br", "img", "hr", "input", "meta", "link", "col", "source", "wbr", "area", "base", "param"}
# Al abrir la llave, se cierran las etiquetas abiertas del conjunto (sin cruzar el límite).
_CIERRA = {
    "tr": ({"td", "th", "tr"}, {"table", "thead", "tbody", "tfoot"}),
    "td": ({"td", "th"}, {"tr", "table"}),
    "th": ({"td", "th"}, {"tr", "table"}),
    "option": ({"option"}, {"select", "datalist"}),
    "li": ({"li"}, {"ul", "ol"}),
    "p": ({"p"}, {"td", "th", "div", "table", "body"}),
    "thead": ({"tbody", "thead", "tr", "td", "th"}, {"table"}),
    "tbody": ({"tbody", "thead", "tr", "td", "th"}, {"table"}),
}
_EN_LINEA_ESPACIO = {"br", "td", "th", "tr", "p", "div", "li", "option", "table"}


@dataclass
class Nodo:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    hijos: list["Nodo | str"] = field(default_factory=list)
    padre: "Nodo | None" = field(default=None, repr=False)

    # ------------------------------------------------------------------ búsqueda

    def iterar(self) -> Iterator["Nodo"]:
        for h in self.hijos:
            if isinstance(h, Nodo):
                yield h
                yield from h.iterar()

    def todos(self, tag: str | None = None, **attrs: str) -> list["Nodo"]:
        """Descendientes con esa etiqueta y esos atributos. `clase` busca dentro de class."""
        out = []
        for n in self.iterar():
            if tag and n.tag != tag:
                continue
            if all(_coincide(n, k, v) for k, v in attrs.items()):
                out.append(n)
        return out

    def primero(self, tag: str | None = None, **attrs: str) -> "Nodo | None":
        for n in self.iterar():
            if (not tag or n.tag == tag) and all(_coincide(n, k, v) for k, v in attrs.items()):
                return n
        return None

    def hijos_tag(self, tag: str) -> list["Nodo"]:
        return [h for h in self.hijos if isinstance(h, Nodo) and h.tag == tag]

    def ancestro(self, tag: str) -> "Nodo | None":
        n = self.padre
        while n is not None and n.tag != tag:
            n = n.padre
        return n

    def attr(self, nombre: str, default: str = "") -> str:
        return self.attrs.get(nombre, default)

    # ------------------------------------------------------------------ tablas

    def filas(self) -> list["Nodo"]:
        """Las tr de esta tabla (no las de tablas anidadas)."""
        out = []
        for n in self.iterar():
            if n.tag == "tr" and n.ancestro("table") is self:
                out.append(n)
        return out

    def celdas(self) -> list["Nodo"]:
        return [h for h in self.hijos if isinstance(h, Nodo) and h.tag in ("td", "th")]

    # ------------------------------------------------------------------ texto

    def texto(self, saltos: bool = False) -> str:
        partes: list[str] = []

        def walk(n: Nodo) -> None:
            for h in n.hijos:
                if isinstance(h, str):
                    partes.append(h)
                elif h.tag in ("script", "style"):
                    continue
                else:
                    if saltos and h.tag in _EN_LINEA_ESPACIO:
                        partes.append("\n")
                    elif h.tag in _EN_LINEA_ESPACIO:
                        partes.append(" ")
                    walk(h)

        walk(self)
        t = "".join(partes).replace("\xa0", " ")
        if saltos:
            lineas = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in t.split("\n")]
            return "\n".join(ln for ln in lineas if ln)
        return re.sub(r"\s+", " ", t).strip()


def _coincide(n: Nodo, k: str, v: str) -> bool:
    if k == "clase":
        return v.lower() in n.attrs.get("class", "").lower().split()
    if k == "nombre":
        return n.attrs.get("name", "") == v
    return n.attrs.get(k.replace("_", "-"), None) == v


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raiz = Nodo("#documento")
        self.pila = [self.raiz]

    def _cerrar_implicitos(self, tag: str) -> None:
        if tag not in _CIERRA:
            return
        cierra, limite = _CIERRA[tag]
        for i in range(len(self.pila) - 1, 0, -1):
            t = self.pila[i].tag
            if t in limite:
                return
            if t in cierra:
                del self.pila[i:]
                return

    def handle_starttag(self, tag, attrs):
        self._cerrar_implicitos(tag)
        padre = self.pila[-1]
        nodo = Nodo(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, padre=padre)
        padre.hijos.append(nodo)
        if tag not in _VACIAS:
            self.pila.append(nodo)

    def handle_startendtag(self, tag, attrs):
        padre = self.pila[-1]
        padre.hijos.append(Nodo(tag, {k.lower(): (v or "") for k, v in attrs}, padre=padre))

    def handle_endtag(self, tag):
        if tag in _VACIAS:
            return
        for i in range(len(self.pila) - 1, 0, -1):
            if self.pila[i].tag == tag:
                del self.pila[i:]
                return
            # </table> no cruza otra tabla abierta más adentro: la cierra también.
            if tag == "table" and self.pila[i].tag == "table":
                break

    def handle_data(self, data):
        self.pila[-1].hijos.append(data)


def parse(documento: str) -> Nodo:
    p = _Parser()
    p.feed(documento)
    p.close()
    return p.raiz


def limpiar(s: str | None) -> str:
    return re.sub(r"\s+", " ", _html.unescape(s or "").replace("\xa0", " ")).strip()

"""HTML de Nexus (editor Froala) a Markdown legible.

Arma un árbol pequeño con HTMLParser y lo recorre: bloques (p, div, listas, tablas,
encabezados) separados por línea en blanco, y en línea negritas, cursivas, ligas e
imágenes. Pensado para que el .md se lea bien tanto en crudo como renderizado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable

_VOID = {"br", "img", "hr", "input", "meta", "link", "col", "source", "wbr"}
_BLOCK = {"p", "div", "section", "article", "header", "footer", "blockquote", "pre", "ul", "ol", "li",
          "table", "thead", "tbody", "tfoot", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
          "figure", "figcaption", "dl", "dt", "dd", "center"}
_IGNORAR = {"script", "style", "head", "title", "iframe", "noscript"}
_VIÑETAS = ("•", "\uf0b7", "·", "▪", "◦", "●", "-", "–")


@dataclass
class Nodo:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    hijos: list["Nodo | str"] = field(default_factory=list)


class _Arbol(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raiz = Nodo("root")
        self.pila = [self.raiz]
        self._ignorando = 0

    def handle_starttag(self, tag, attrs):
        if tag in _IGNORAR:
            self._ignorando += 1
            return
        if self._ignorando:
            return
        nodo = Nodo(tag, {k: (v or "") for k, v in attrs})
        self.pila[-1].hijos.append(nodo)
        if tag not in _VOID:
            self.pila.append(nodo)

    def handle_startendtag(self, tag, attrs):
        if not self._ignorando and tag not in _IGNORAR:
            self.pila[-1].hijos.append(Nodo(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        if tag in _IGNORAR:
            self._ignorando = max(0, self._ignorando - 1)
            return
        if self._ignorando or tag in _VOID:
            return
        for i in range(len(self.pila) - 1, 0, -1):
            if self.pila[i].tag == tag:
                del self.pila[i:]
                return

    def handle_data(self, data):
        if not self._ignorando:
            self.pila[-1].hijos.append(data)


class Conversor:
    def __init__(self, imagen: Callable[[str, str], str] | None = None, nivel_base: int = 3) -> None:
        # imagen(src, alt) -> ruta a usar en el .md (p. ej. la copia local)
        self.imagen = imagen
        self.nivel_base = nivel_base

    # ------------------------------------------------------------------ en línea

    def _en_linea(self, nodos: list[Nodo | str]) -> str:
        partes: list[str] = []
        for n in nodos:
            if isinstance(n, str):
                partes.append(re.sub(r"\s+", " ", n.replace("\xa0", " ")))
                continue
            t = n.tag
            if t == "br":
                partes.append("\n")
            elif t in ("strong", "b"):
                partes.append(_envolver(self._en_linea(n.hijos), "**"))
            elif t in ("em", "i"):
                partes.append(_envolver(self._en_linea(n.hijos), "*"))
            elif t in ("s", "strike", "del"):
                partes.append(_envolver(self._en_linea(n.hijos), "~~"))
            elif t == "a":
                partes.append(self._liga(n))
            elif t == "img":
                partes.append(self._img(n))
            elif t in ("sup", "sub", "span", "font", "u", "small", "big", "mark", "abbr", "label", "code"):
                txt = self._en_linea(n.hijos)
                partes.append(f"`{txt.strip()}`" if t == "code" and txt.strip() else txt)
            elif t in _BLOCK:
                # Bloque dentro de un contexto en línea (p. ej. <p> dentro de <li>): salto.
                partes.append("\n" + self._en_linea(n.hijos) + "\n")
            else:
                partes.append(self._en_linea(n.hijos))
        return "".join(partes)

    def _liga(self, n: Nodo) -> str:
        href = (n.attrs.get("href") or "").strip()
        texto = self._en_linea(n.hijos).strip()
        if not href or href.startswith("javascript:"):
            return texto
        href = href.replace(" ", "%20")
        if not texto or texto.rstrip("/") == href.rstrip("/"):
            return f"<{href}>"
        return f"[{texto}]({href})"

    def _img(self, n: Nodo) -> str:
        src = (n.attrs.get("src") or "").strip()
        if not src or src.startswith("data:"):
            return ""
        alt = (n.attrs.get("alt") or "imagen").strip() or "imagen"
        ruta = self.imagen(src, alt) if self.imagen else src
        if "://" not in ruta and " " in ruta:
            return f"![{alt}](<{ruta}>)"
        return f"![{alt}]({ruta.replace(' ', '%20')})"

    # ------------------------------------------------------------------ bloques

    def bloques(self, nodos: list[Nodo | str]) -> list[str]:
        out: list[str] = []
        linea: list[Nodo | str] = []

        def cerrar_linea():
            if linea:
                txt = _limpiar(self._en_linea(linea))
                if txt:
                    out.append(txt)
                linea.clear()

        for n in nodos:
            if isinstance(n, str) or n.tag not in _BLOCK:
                linea.append(n)
                continue
            cerrar_linea()
            out.extend(self._bloque(n))
        cerrar_linea()
        return out

    def _bloque(self, n: Nodo) -> list[str]:
        t = n.tag
        if t in ("h1", "h2", "h3", "h4", "h5", "h6"):
            nivel = min(6, self.nivel_base + int(t[1]) - 1)
            txt = _limpiar(self._en_linea(n.hijos)).replace("\n", " ")
            return [f"{'#' * nivel} {txt}"] if txt else []
        if t in ("ul", "ol"):
            return [self._lista(n, 0)]
        if t == "table":
            return [self._tabla(n)]
        if t == "hr":
            return ["---"]
        if t == "blockquote":
            interior = "\n\n".join(self.bloques(n.hijos))
            return ["\n".join("> " + ln if ln else ">" for ln in interior.splitlines())] if interior else []
        if t == "pre":
            txt = "".join(_texto_plano(n))
            return [f"```\n{txt.strip()}\n```"] if txt.strip() else []
        return self.bloques(n.hijos)

    def _lista(self, n: Nodo, nivel: int) -> str:
        items: list[str] = []
        num = 1
        try:
            num = int(n.attrs.get("start") or 1)
        except ValueError:
            pass
        for li in n.hijos:
            if isinstance(li, str) or li.tag != "li":
                if isinstance(li, Nodo) and li.tag in ("ul", "ol"):
                    items.append(self._lista(li, nivel + 1))
                continue
            marca = f"{num}." if n.tag == "ol" else "-"
            num += 1
            sub = [h for h in li.hijos if isinstance(h, Nodo) and h.tag in ("ul", "ol")]
            resto = [h for h in li.hijos if not (isinstance(h, Nodo) and h.tag in ("ul", "ol"))]
            cuerpo = "\n\n".join(self.bloques(resto)).strip()
            sangria = " " * (len(marca) + 1)
            cuerpo = cuerpo.replace("\n", "\n" + "  " * nivel + sangria)
            items.append(f"{'  ' * nivel}{marca} {cuerpo}".rstrip())
            for s in sub:
                items.append(self._lista(s, nivel + 1))
        return "\n".join(i for i in items if i.strip())

    def _tabla(self, n: Nodo) -> str:
        filas: list[list[str]] = []

        def recorrer(x: Nodo):
            for h in x.hijos:
                if isinstance(h, Nodo):
                    if h.tag == "tr":
                        celdas = []
                        for c in h.hijos:
                            if isinstance(c, Nodo) and c.tag in ("td", "th"):
                                txt = " ".join(b.replace("\n", " ") for b in self.bloques(c.hijos))
                                celdas.append(txt.replace("|", "\\|").strip())
                        if any(celdas):
                            filas.append(celdas)
                    else:
                        recorrer(h)

        recorrer(n)
        if not filas:
            return ""
        ancho = max(len(f) for f in filas)
        filas = [f + [""] * (ancho - len(f)) for f in filas]
        if ancho == 1:
            return "\n\n".join(f[0] for f in filas)
        lineas = ["| " + " | ".join(filas[0]) + " |", "|" + "---|" * ancho]
        lineas += ["| " + " | ".join(f) + " |" for f in filas[1:]]
        return "\n".join(lineas)

    def convertir(self, html: str | None) -> str:
        if not html or not html.strip():
            return ""
        p = _Arbol()
        p.feed(html)
        p.close()
        bloques = [b for b in self.bloques(p.raiz.hijos) if b.strip()]
        return _unir(bloques)


def html_a_md(html: str | None, imagen: Callable[[str, str], str] | None = None, nivel_base: int = 3) -> str:
    return Conversor(imagen, nivel_base).convertir(html)


# ---------------------------------------------------------------------- utilidades


def _envolver(txt: str, marca: str) -> str:
    """**negrita** con los espacios afuera: '**Recursos **' no es Markdown válido."""
    if not txt.strip():
        return txt
    izq = txt[: len(txt) - len(txt.lstrip())]
    der = txt[len(txt.rstrip()):]
    interior = txt.strip()
    if interior.startswith(marca) and interior.endswith(marca):
        return txt
    return f"{izq}{marca}{interior}{marca}{der}"


def _limpiar(txt: str) -> str:
    lineas = [re.sub(r"[ \t]+", " ", ln).strip() for ln in txt.split("\n")]
    # ****: negritas pegadas que quedaron vacías o contiguas.
    lineas = [re.sub(r"\*\*\s*\*\*", "", ln) for ln in lineas]
    salida: list[str] = []
    for ln in lineas:
        if ln or (salida and salida[-1]):
            salida.append(ln)
    while salida and not salida[-1]:
        salida.pop()
    # Saltos <br> dentro de un párrafo: dos espacios = salto duro en Markdown.
    return "  \n".join(salida) if all(salida) else "\n".join(salida)


def _texto_plano(n: Nodo) -> list[str]:
    out: list[str] = []
    for h in n.hijos:
        if isinstance(h, str):
            out.append(h)
        elif h.tag == "br":
            out.append("\n")
        else:
            out.extend(_texto_plano(h))
    return out


_ES_ITEM = re.compile(r"^(\d{1,2}[.)]|[-*+])\s")


def _unir(bloques: list[str]) -> str:
    """Une bloques con línea en blanco, salvo renglones de lista seguidos (Nexus suele
    escribir cada viñeta o cada '1.' como un <p> aparte). Las viñetas que siguen a un
    paso numerado se anidan bajo él."""
    normal: list[str] = []
    for b in bloques:
        for v in _VIÑETAS:
            if b.startswith(v) and len(b) > len(v) and (v not in ("-", "–") or b[len(v)] == " "):
                b = "- " + b[len(v):].lstrip()
                break
        normal.append(b)
    out = ""
    previo = ""
    en_numerada = False
    for b in normal:
        es_item = bool(_ES_ITEM.match(b)) and "\n\n" not in b
        numerado = es_item and b[0].isdigit()
        if es_item and numerado:
            en_numerada = True
        elif not es_item:
            en_numerada = False
        if es_item and not numerado and en_numerada:
            b = "   " + b.replace("\n", "\n   ")
        if not out:
            out = b
        elif es_item and _ES_ITEM.match(previo.lstrip()) and "\n\n" not in previo:
            out += "\n" + b
        else:
            out += "\n\n" + b
        previo = b
    out = re.sub(r"\*\* ([\"”.,;:)])", r"**\1", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()

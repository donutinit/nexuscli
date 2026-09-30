"""Copia local de un curso de Nexus: instrucciones, rúbricas y recursos de cada tarea.

Estructura:

    <carpeta del curso>/
      README.md                 índice de actividades
      .nexuscli.json            manifiesto: qué archivo vino de qué documento de Nexus
      generales/                programa analítico, bienvenida, avisos, recursos sueltos
      1.1/ 1.2/ ... pia/        una carpeta por actividad
        instrucciones.md
        rubrica.md              si la actividad usa rúbrica
        recursos.md             archivos, enlaces y lecturas de la pestaña Recursos
        retroalimentacion.md    solo con --personal: calificación, comentarios, entregas
        img/                    imágenes de las instrucciones
        *.pdf ...               los archivos de la pestaña Recursos

Sincroniza: si lo vuelves a correr solo baja lo que falta o cambió en Nexus y solo reescribe
los .md cuyo contenido cambió. Nunca borra: lo que desaparece de Nexus se reporta, y los
archivos agregados a mano se listan en recursos.md como material extra.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from . import config, texto
from .client import NexusError
from .estilo import pintar
from .markdown import html_a_md
from .nexus import PIA, Curso, Nexus, Tarea

MANIFIESTO = ".nexuscli.json"
GENERADOS = {"README.md", "instrucciones.md", "rubrica.md", "recursos.md", "retroalimentacion.md", "avisos.md",
             "bienvenida.md"}

_TIPOS = [
    ("RecursoArchivos", "archivo"),
    ("RecursosExternos", "externo"),
    ("RecursosWeb", "web"),
    ("RecursosLibros", "libro"),
    ("RecursosArticulos", "artículo"),
    ("RecursosTextos", "texto"),
    ("RecursosHTML", "html"),
    ("RecursoScorm", "scorm"),
]


# ---------------------------------------------------------------------- nombres


_CONT = "\x80-\xbf€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ"
_MOJIBAKE = re.compile(f"[\u00c2-\u00df][{_CONT}]|[\u00e0-\u00ef][{_CONT}]{{2}}")


def arreglar_mojibake(s: str) -> str:
    """'pÃ¡g.' -> 'pág.': texto UTF-8 que alguien guardó como Latin-1/cp1252. Corrige cada
    secuencia rota por separado, así no estorban los acentos que sí estaban bien."""
    if not s or not _MOJIBAKE.search(s):
        return s

    def uno(m: re.Match) -> str:
        frag = m.group(0)
        for enc in ("cp1252", "latin-1"):
            try:
                return frag.encode(enc).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        return frag

    return _MOJIBAKE.sub(uno, s)


def nombre_archivo(nombre: str, respaldo: str = "archivo") -> str:
    n = arreglar_mojibake(nombre or "").strip()
    n = re.sub(r"[/\\\x00-\x1f:*?\"<>|]", "-", n)
    # Solo espacios en los extremos y puntos al inicio (archivo oculto); "moderno..pdf" se respeta.
    n = re.sub(r"\s+", " ", n).strip().lstrip(".")
    if not n or not n.strip("."):
        n = respaldo
    stem, dot, ext = n.rpartition(".")
    if not dot or len(ext) > 6:
        stem, ext = n, ""
    # Linux admite 255 bytes por nombre; se recorta el stem por bytes, sin partir caracteres.
    limite = 240 - len(ext.encode()) - 1
    while len(stem.encode()) > limite:
        stem = stem[:-1]
    stem = stem.rstrip()
    return f"{stem}.{ext}" if ext else stem


def carpeta_tarea(t: Tarea) -> str:
    return "pia" if t.tipo == PIA else nombre_archivo(t.clave.lower(), str(t.id))


def dueno(destino: Path) -> tuple[int, str] | None:
    """(CursoId, nombre) de la materia clonada en esa carpeta, según su manifiesto."""
    try:
        m = json.loads((destino / MANIFIESTO).read_text(encoding="utf-8"))
        return int(m["curso_id"]), m.get("curso") or ""
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return None


def liga_md(ruta: str) -> str:
    """Destino de liga Markdown legible en crudo: <ruta con espacios> (CommonMark)."""
    if re.search(r"[\s()<>]", ruta):
        return "<" + ruta.replace("<", "%3C").replace(">", "%3E") + ">"
    return ruta


def partes_curso(nombre: str) -> tuple[str, str, str]:
    """'Análisis audiovisual | AGO26 | 101' -> ('Análisis audiovisual', 'AGO26', '101')."""
    p = [x.strip() for x in (nombre or "").split("|")] + ["", ""]
    return p[0], p[1], p[2]


# ---------------------------------------------------------------------- resultado


@dataclass
class Resumen:
    bajados: list[str] = field(default_factory=list)
    copiados: list[str] = field(default_factory=list)
    sin_cambio: int = 0
    bytes: int = 0
    escritos: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    desaparecidos: list[str] = field(default_factory=list)
    actividades: int = 0

    def as_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------- clonador


class Clonador:
    def __init__(
        self,
        nx: Nexus,
        destino: Path,
        *,
        archivos: bool = True,
        personal: bool = False,
        ocultos: bool = False,
        log: Callable[[str], None] = print,
    ) -> None:
        self.nx = nx
        self.dir = destino
        self.archivos = archivos
        self.personal = personal
        self.ocultos = ocultos
        self.log = log
        self.r = Resumen()
        self.man = self._leer_manifiesto()
        self._vigentes: set[str] = set()      # rutas de archivos de Nexus vistas en esta corrida
        self._por_doc: dict[int, Path] = {}   # DocumentoId -> archivo ya en disco en esta corrida
        self._ids_tareas: set[tuple[str, int]] = set()  # recursos que ya están en alguna actividad

    # ------------------------------------------------------------------ manifiesto

    def _leer_manifiesto(self) -> dict:
        try:
            m = json.loads((self.dir / MANIFIESTO).read_text(encoding="utf-8"))
            m.setdefault("archivos", {})
            m.setdefault("imagenes", {})
            return m
        except (FileNotFoundError, ValueError):
            return {"version": 1, "archivos": {}, "imagenes": {}}

    def _guardar_manifiesto(self, curso: Curso, comando: str | None) -> None:
        hubo_cambios = bool(self.r.bajados or self.r.copiados or self.r.escritos)
        if hubo_cambios or "sincronizado" not in self.man:
            self.man["sincronizado"] = texto.ahora().isoformat(timespec="minutes")
        self.man.update({"curso_id": curso.id, "curso": curso.nombre})
        if comando:
            self.man["comando"] = comando
        self.man["archivos"] = dict(sorted(self.man["archivos"].items()))
        nuevo = json.dumps(self.man, ensure_ascii=False, indent=1) + "\n"
        path = self.dir / MANIFIESTO
        if not path.exists() or path.read_text(encoding="utf-8") != nuevo:
            path.write_text(nuevo, encoding="utf-8")

    # ------------------------------------------------------------------ escritura

    def _escribir(self, rel: str, contenido: str) -> None:
        path = self.dir / rel
        contenido = arreglar_mojibake(contenido).rstrip() + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == contenido:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contenido, encoding="utf-8")
        self.r.escritos.append(rel)

    def _bajar(self, doc: dict, rel: str) -> str:
        """Pone el documento de Nexus en `rel` (relativa a la carpeta del curso). Devuelve la
        ruta final, que puede cambiar si ya había un archivo ajeno con ese nombre."""
        doc_id = int(doc["DocumentoId"])
        peso = doc.get("Peso")
        path = self.dir / rel
        entrada = self.man["archivos"].get(rel)

        def al_dia(p: Path) -> bool:
            return p.exists() and (not peso or p.stat().st_size == int(peso))

        if entrada and entrada.get("documento_id") == doc_id and al_dia(path):
            self.r.sin_cambio += 1
        elif not self.archivos:
            return rel
        else:
            if path.exists() and not entrada:
                if al_dia(path):
                    # Ya estaba (copia hecha a mano o por otra herramienta): se adopta.
                    self.r.sin_cambio += 1
                    self._registrar(rel, doc)
                    return rel
                # Un archivo ajeno con el mismo nombre: no se pisa.
                stem, ext = path.stem, path.suffix
                rel = str(Path(rel).with_name(f"{stem} (Nexus){ext}"))
                path = self.dir / rel
                if self.man["archivos"].get(rel, {}).get("documento_id") == doc_id and al_dia(path):
                    self.r.sin_cambio += 1
                    self._registrar(rel, doc)
                    return rel
            origen = self._por_doc.get(doc_id)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                if origen and origen.exists() and origen != path:
                    shutil.copy2(origen, path)
                    self.r.copiados.append(rel)
                else:
                    self.nx.c.descargar(doc["URL"], path)
                    self.r.bajados.append(rel)
                    self.r.bytes += path.stat().st_size
            except (NexusError, OSError) as e:
                self.r.errores.append(f"{rel}: {e}")
                return rel
        self._registrar(rel, doc)
        return rel

    def _registrar(self, rel: str, doc: dict) -> None:
        doc_id = int(doc["DocumentoId"])
        self.man["archivos"][rel] = {"documento_id": doc_id, "peso": doc.get("Peso"), "url": doc.get("URL")}
        self._vigentes.add(rel)
        self._por_doc.setdefault(doc_id, self.dir / rel)

    def _imagen(self, carpeta: str) -> Callable[[str, str], str]:
        """Callback para html_a_md: baja las imágenes alojadas en Nexus a <carpeta>/img/."""

        def cb(src: str, alt: str) -> str:
            url = src.strip()
            host = urlparse(url).hostname or ""
            if not host.endswith("uanl.mx") or not self.archivos:
                return url
            rel_url = unquote(urlparse(url).path).lstrip("/")
            conocida = self.man["imagenes"].get(url)
            destino = conocida or f"{carpeta}/img/{nombre_archivo(Path(rel_url).name, 'imagen')}"
            path = self.dir / destino
            if not path.exists():
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self.nx.c.descargar(rel_url, path)
                    self.r.bajados.append(destino)
                    self.r.bytes += path.stat().st_size
                except (NexusError, OSError) as e:
                    self.r.errores.append(f"{destino}: {e}")
                    return url
            self.man["imagenes"][url] = destino
            self._vigentes.add(destino)
            return str(Path(destino).relative_to(carpeta)) if destino.startswith(carpeta + "/") else "../" + destino

        return cb

    # ------------------------------------------------------------------ recursos

    def _visible(self, r: dict) -> bool:
        return self.ocultos or r.get("MostrarEstudiante") is not False

    def _recursos(self, rec: dict, carpeta: str) -> dict[str, list]:
        """Baja los archivos y ordena el resto. Devuelve {'archivos': [(rel, doc, r)], 'enlaces':
        [...], 'lecturas': [...], 'referencias': [...], 'scorm': [...]}"""
        out: dict[str, list] = {"archivos": [], "enlaces": [], "lecturas": [], "referencias": [], "scorm": []}
        usados: dict[str, int] = {}
        archivos = sorted(
            (r for r in rec.get("RecursoArchivos") or [] if self._visible(r) and (r.get("Documento") or {}).get("URL")),
            key=lambda r: (r.get("Posicion") or 0, r["Documento"]["DocumentoId"]),
        )
        for r in archivos:
            doc = r["Documento"]
            nombre = nombre_archivo(doc.get("Nombre") or "", f"documento-{doc['DocumentoId']}")
            if doc.get("Extension") and not Path(nombre).suffix:
                nombre += doc["Extension"]
            base, n = nombre, 2
            while nombre in usados and usados[nombre] != doc["DocumentoId"]:
                nombre = f"{Path(base).stem} ({n}){Path(base).suffix}"
                n += 1
            usados[nombre] = doc["DocumentoId"]
            rel = self._bajar(doc, f"{carpeta}/{nombre}" if carpeta else nombre)
            out["archivos"].append((rel, doc, r))
        for clave, tipo in _TIPOS[1:]:
            for r in sorted(rec.get(clave) or [], key=lambda r: r.get("Posicion") or 0):
                if not self._visible(r):
                    continue
                if tipo in ("externo", "web"):
                    out["enlaces"].append((tipo, r))
                elif tipo in ("texto", "html"):
                    out["lecturas"].append((tipo, r))
                elif tipo == "scorm":
                    out["scorm"].append(r)
                else:
                    out["referencias"].append((tipo, r))
        return out

    def _md_recursos(self, titulo: str | None, rs: dict[str, list], carpeta: str, extra: list[str],
                     nivel: str = "##") -> str:
        l = [f"# {titulo}", ""] if titulo else []
        if titulo and not any(rs.values()) and not extra:
            l.append("Nexus no tiene recursos para esta actividad.")
        if rs["archivos"]:
            l += [f"{nivel} Archivos", ""]
            for rel, doc, r in rs["archivos"]:
                local = rel[len(carpeta) + 1:] if carpeta and rel.startswith(carpeta + "/") else rel
                marca = " · oculto para estudiantes" if r.get("MostrarEstudiante") is False else ""
                l.append(f"- [{Path(local).name}]({liga_md(local)}) · {texto.tamano(doc.get('Peso'))}{marca}")
            l.append("")
        if rs["enlaces"]:
            l += [f"{nivel} Enlaces", ""]
            for _tipo, r in rs["enlaces"]:
                l.append("- " + _enlace(r))
            l.append("")
        if rs["referencias"]:
            l += [f"{nivel} Referencias", ""]
            for tipo, r in rs["referencias"]:
                l.append(f"- {_referencia(r)} ({tipo})")
            l.append("")
        if rs["lecturas"]:
            l += [f"{nivel} Lecturas", ""]
            img = self._imagen(carpeta or "generales")
            for _tipo, r in rs["lecturas"]:
                t = arreglar_mojibake(texto.html_a_texto(r.get("Titulo") or "")) or "Sin título"
                l += [f"{nivel}# {t}", "", html_a_md(r.get("Contenido"), img, nivel_base=len(nivel) + 2) or "(vacío)", ""]
        if rs["scorm"]:
            l += [f"{nivel} Paquetes SCORM", "", "Solo se pueden abrir dentro de Nexus.", ""]
            for r in rs["scorm"]:
                l.append(f"- {r.get('Titulo') or r.get('Nombre') or r.get('ScormId')}")
            l.append("")
        if extra:
            l += [f"{nivel} Material agregado a mano", "", "Estos archivos están en la carpeta pero no vienen de Nexus.", ""]
            for e in extra:
                l.append(f"- [{e}]({liga_md(e)})")
            l.append("")
        return "\n".join(l)

    def _extra(self, carpeta: str) -> list[str]:
        """Archivos de la carpeta que no son de Nexus ni generados."""
        base = self.dir / carpeta
        if not base.is_dir():
            return []
        nuestros = {Path(r).name for r in self.man["archivos"] if str(Path(r).parent) == carpeta}
        out = []
        for p in sorted(base.iterdir()):
            if p.is_file() and not p.name.startswith(".") and p.name not in GENERADOS and p.name not in nuestros:
                out.append(p.name)
        return out

    # ------------------------------------------------------------------ tareas

    def tarea(self, t: Tarea, seleccion: set[int] | None = None) -> dict:
        carpeta = carpeta_tarea(t)
        det = self.nx.detalle_tarea(t)
        rec = self.nx.recursos_tarea(t)
        for clave, _tipo in _TIPOS:
            for r in rec.get(clave) or []:
                self._ids_tareas.add(_id_recurso(clave, r))
        rub = self.nx.rubrica(t) if t.usa_rubrica else {}
        rs = self._recursos(rec, carpeta)
        img = self._imagen(carpeta)
        titulo = f"{t.clave} · {t.nombre}" if t.clave != "PIA" else t.nombre

        self._escribir(f"{carpeta}/instrucciones.md", self._md_instrucciones(t, det, rs, bool(rub), img, titulo))
        if rub and rub.get("Criterios"):
            self._escribir(f"{carpeta}/rubrica.md", _md_rubrica(t, rub, titulo, seleccion if self.personal else None))
        self._escribir(f"{carpeta}/recursos.md",
                       self._md_recursos(f"Recursos · {titulo}", rs, carpeta, self._extra(carpeta)))
        if self.personal and (t.calificacion is not None or t.retros or t.entregas_activas):
            self._escribir(f"{carpeta}/retroalimentacion.md", self._md_retro(t, rub, seleccion, titulo, carpeta))
        self.r.actividades += 1
        return {"carpeta": carpeta, "archivos": len(rs["archivos"]), "enlaces": len(rs["enlaces"]),
                "lecturas": len(rs["lecturas"]), "rubrica": bool(rub and rub.get("Criterios"))}

    def _md_instrucciones(self, t: Tarea, det: dict, rs: dict, hay_rubrica: bool, img, titulo: str) -> str:
        nombre, periodo, grupo = partes_curso(t.curso)
        cab = f"**{nombre}**" + (f" · {periodo}" if periodo else "") + (f" · grupo {grupo}" if grupo else "")
        fila = lambda k, v: f"| {k} | {v} |"
        l = [f"# {titulo}", "", cab, "", "| | |", "|---|---|"]
        l.append(fila("Abre", texto.fmt_fecha(t.inicio, anio=True)))
        cierre = texto.fmt_fecha(t.cierre, anio=True)
        otra = t.fin if t.cierre == t.limite else t.limite
        if otra and t.cierre and otra != t.cierre and not t.extemporanea:
            cierre += f" (Nexus también marca {texto.fmt_fecha(otra, anio=True)}; vale la más temprana)"
        l.append(fila("Cierra", cierre))
        if t.extemporanea and t.limite:
            l.append(fila("Entrega extemporánea", f"hasta {texto.fmt_fecha(t.limite, anio=True)}"))
        l.append(fila("Valor", f"{t.valor:g} pts" if t.valor is not None else "-"))
        l.append(fila("Modalidad", "En equipo" if t.en_equipo else "Individual"))
        acepta = [x for x, ok in (("archivos", t.acepta_archivos), ("ligas", t.acepta_ligas)) if ok]
        l.append(fila("Se entrega como", " o ".join(acepta) or "no se entrega en Nexus"))
        if hay_rubrica:
            l.append(fila("Rúbrica", "[rubrica.md](rubrica.md)"))
        n_arch, n_enl, n_lec = len(rs["archivos"]), len(rs["enlaces"]), len(rs["lecturas"])
        cuenta = ", ".join(x for x in (_plural(n_arch, "archivo"), _plural(n_enl, "enlace"), _plural(n_lec, "lectura")) if x)
        l.append(fila("Recursos", f"{cuenta or 'ninguno'} · [recursos.md](recursos.md)"))
        extras = []
        if det.get("UsaLTI"):
            extras.append("usa un servicio LTI (p. ej. Turnitin)")
        if det.get("UsaCoevaluacion"):
            extras.append("tiene coevaluación")
        if extras:
            l.append(fila("Además", "; ".join(extras)))
        l.append(fila("Nexus", f"elemento {t.id}"))
        l.append("")
        contenidos = sorted(det.get("Contenidos") or [], key=lambda c: c.get("Posicion") or 0)
        for c in contenidos:
            if c.get("Estado") is False:
                continue
            cuerpo = html_a_md(c.get("Descripcion"), img, nivel_base=3)
            if cuerpo:
                l += [f"## {(c.get('Titulo') or 'Contenido').strip()}", "", cuerpo, ""]
        if not contenidos:
            l += ["Nexus no tiene instrucciones escritas para esta actividad.", ""]
        if det.get("Justificacion"):
            l += ["## Justificación", "", html_a_md(det["Justificacion"], img) or str(det["Justificacion"]), ""]
        temas = det.get("Tema") or det.get("Temas") or []
        temas = [x for x in ([temas] if isinstance(temas, dict) else temas) if isinstance(x, dict)]
        temas = [(x.get("Tema") if isinstance(x.get("Tema"), dict) else x) for x in temas]
        temas = [x for x in temas if x and x.get("TemaId")]
        if temas:
            l += ["## Foro vinculado", ""]
            for tema in temas:
                l += [f"**{tema.get('Nombre')}** (tema {tema['TemaId']}; `nexuscli foro {tema['TemaId']}`)", ""]
                if tema.get("Mensaje"):
                    l += [html_a_md(tema["Mensaje"], img), ""]
        examenes = det.get("EvidenciaExamenes") or det.get("Examenes") or []
        if examenes:
            l += ["## Exámenes vinculados", ""]
            for ex in examenes:
                e = ex.get("Examen") or ex
                l.append(f"- {e.get('Nombre') or e.get('ExamenId')}")
            l.append("")
        return "\n".join(l)

    def _md_retro(self, t: Tarea, rub: dict, seleccion: set[int] | None, titulo: str, carpeta: str) -> str:
        l = [f"# Retroalimentación · {titulo}", ""]
        if t.calificacion is not None:
            pts = (t.calificacion * (t.valor or 0) / 100) if t.valor else None
            l.append(f"**Calificación:** {round(t.calificacion, 2):g} / 100"
                     + (f" · {round(pts, 2):g} de {t.valor:g} pts" if pts is not None else ""))
        else:
            l.append("**Calificación:** todavía no")
        l.append("")
        if rub.get("Criterios") and seleccion:
            l += ["## Rúbrica", "", "| Criterio | Nivel | Puntos |", "|---|---|---:|"]
            for crit, nivel, puntos, _max in _niveles_elegidos(rub, seleccion):
                l.append(f"| {crit} | {nivel} | {puntos:g} de {_max:g} |")
            l.append("")
        if t.retros:
            l += ["## Comentarios del profesor", ""]
            for r in sorted(t.retros, key=lambda r: r.get("FechaModificacion") or ""):
                fecha = texto.fmt_fecha(texto.fecha(r.get("FechaModificacion")), anio=True)
                l += [f"### {fecha}", "", html_a_md(r.get("Descripcion")) or texto.html_a_texto(r.get("Descripcion")), ""]
                for rep in r.get("Replicas") or []:
                    l += ["> " + texto.html_a_texto(rep.get("Comentario")).replace("\n", "\n> "), ""]
        if t.entregas_activas:
            l += ["## Entregas", ""]
            for e in t.entregas_activas:
                doc = e.get("Documento") or {}
                ext = e.get("RecursoExterno") or {}
                modo = "en equipo" if e.get("EnEquipo") else "individual"
                if doc.get("URL") and self.archivos:
                    rel = self._bajar(doc, f"{carpeta}/entregas/{nombre_archivo(doc.get('Nombre') or '', str(doc['DocumentoId']))}")
                    local = rel[len(carpeta) + 1:]
                    l.append(f"- [{Path(local).name}]({liga_md(local)}) · {texto.tamano(doc.get('Peso'))} · {modo} · "
                             f"{texto.fmt_fecha(texto.fecha(doc.get('FechaCreacion')), anio=True)}")
                elif ext.get("Contenido"):
                    l.append(f"- [{ext.get('Titulo') or ext['Contenido']}]({ext['Contenido']}) · {modo}")
                else:
                    l.append(f"- {doc.get('Nombre') or '?'} · {modo}")
            l.append("")
        return "\n".join(l)

    # ------------------------------------------------------------------ curso

    def curso(self, curso: Curso, solo: Tarea | None = None, comando: str | None = None) -> Resumen:
        self.dir.mkdir(parents=True, exist_ok=True)
        if comando:
            self.man["comando"] = comando
        tareas = self.nx.tareas(curso)
        seleccion = self.nx.calificacion_rubrica(curso.id) if self.personal else {}
        objetivo = [t for t in tareas if solo is None or (t.tipo, t.id) == (solo.tipo, solo.id)]
        filas = []
        for t in objetivo:
            info = self.tarea(t, seleccion.get((t.tipo, t.id)))
            filas.append((t, info))
            partes = [_plural(info["archivos"], "archivo"), _plural(info["enlaces"], "enlace"),
                      _plural(info["lecturas"], "lectura"), "rúbrica" if info["rubrica"] else ""]
            carpeta = f"{info['carpeta']:<5}"
            detalle = " · ".join(p for p in partes if p) or "sin recursos"
            self.log(f"  {pintar(carpeta, 'hueso')} {texto.recortar(t.nombre, 50):<50}  {pintar(detalle, 'tenue')}")
        if solo is None:
            self._generales(curso, filas)
            self._indice(curso, filas)
            # Lo que el manifiesto conocía y ya no está en Nexus.
            for rel in list(self.man["archivos"]):
                if rel not in self._vigentes:
                    self.r.desaparecidos.append(rel)
                    self.man["archivos"][rel]["ya_no_esta_en_nexus"] = True
        self._guardar_manifiesto(curso, comando)
        return self.r

    def _generales(self, curso: Curso, filas: list[tuple[Tarea, dict]]) -> None:
        g = "generales"
        det = self.nx.detalle_curso(curso.id)
        img = self._imagen(g)
        l = [f"# Generales · {texto.curso_corto(curso.nombre)}", ""]

        prog = {}
        try:
            prog = self.nx.programa(curso.id)
        except NexusError as e:
            self.r.errores.append(f"programa analítico: {e}")
        docs_prog = []
        for clave, etiqueta in (("Archivo", "Programa analítico"), ("RepresentaionGrafica", "Representación gráfica"),
                                ("RepresentacionGrafica", "Representación gráfica"), ("MapaConceptual", "Mapa conceptual")):
            doc = ((prog.get(clave) or {}).get("Documento")) or {}
            if doc.get("URL") and (prog.get(clave) or {}).get("Estado", True):
                rel = self._bajar(doc, f"{g}/{nombre_archivo(doc.get('Nombre') or etiqueta)}")
                docs_prog.append((etiqueta, rel, doc))
        if docs_prog:
            l += ["## Programa analítico", ""]
            for etiqueta, rel, doc in docs_prog:
                local = rel[len(g) + 1:]
                l.append(f"- {etiqueta}: [{Path(local).name}]({liga_md(local)}) · {texto.tamano(doc.get('Peso'))}")
            l.append("")

        fuente = {**curso.raw, **{k: v for k, v in det.items() if v}}
        bienvenida = html_a_md((fuente.get("Bienvenida") or {}).get("Contenido"), img)
        compromiso = html_a_md((fuente.get("Compromiso") or {}).get("Descripcion"), img)
        if bienvenida or compromiso:
            b = [f"# Bienvenida · {texto.curso_corto(curso.nombre)}", ""]
            if bienvenida:
                b += [bienvenida, ""]
            if compromiso:
                b += ["## Compromiso del estudiante", "", compromiso, ""]
            self._escribir(f"{g}/bienvenida.md", "\n".join(b))
            l += ["## Bienvenida", "", "[bienvenida.md](bienvenida.md): mensaje del profesor"
                  + (" y compromiso del estudiante" if compromiso else "") + ".", ""]

        avisos = self.nx.avisos(curso.id)
        if avisos:
            a = [f"# Avisos · {texto.curso_corto(curso.nombre)}", "",
                 "Los que Nexus tenía vigentes en la última sincronización.", ""]
            for av in sorted(avisos, key=lambda x: x.get("FechaInicio") or "", reverse=True):
                urg = " · urgente" if av.get("EsUrgente") else ""
                a += [f"## {av.get('Titulo')}", "",
                      f"*{texto.fmt_fecha(texto.fecha(av.get('FechaInicio')), False, True)} a "
                      f"{texto.fmt_fecha(texto.fecha(av.get('FechaFin')), False, True)}{urg}*", "",
                      html_a_md(av.get("Mensaje"), img), ""]
            self._escribir(f"{g}/avisos.md", "\n".join(a))
            l += ["## Avisos", "", f"[avisos.md](avisos.md) · {_plural(len(avisos), 'aviso vigente', 'avisos vigentes')}", ""]

        # Recursos del curso que no están en ninguna actividad.
        todos = self.nx.recursos(curso.id)
        sueltos: dict[str, list] = {}
        for clave, _tipo in _TIPOS:
            for r in todos.get(clave) or []:
                if _id_recurso(clave, r) not in self._ids_tareas:
                    sueltos.setdefault(clave, []).append(r)
        rs = self._recursos(sueltos, g)
        if any(rs.values()):
            l += ["## Recursos del curso que no son de una actividad", "",
                  self._md_recursos(None, rs, g, [], nivel="###").strip(), ""]
        extra = self._extra(g)
        if extra:
            l += ["## Material agregado a mano", ""] + [f"- [{e}]({liga_md(e)})" for e in extra] + [""]
        self._escribir(f"{g}/README.md", "\n".join(l))

    def _indice(self, curso: Curso, filas: list[tuple[Tarea, dict]]) -> None:
        nombre, periodo, grupo = partes_curso(curso.nombre)
        titulo = nombre + (f" · {periodo}" if periodo else "") + (f" · grupo {grupo}" if grupo else "")
        profes = ", ".join(_persona(p) for p in curso.profesores) or "-"
        det = self.nx.detalle_curso(curso.id)
        modalidad = (det.get("Modalidad") or {}).get("Nombre")
        l = [f"# {titulo}", ""]
        l.append(f"Imparte: {profes}" + (f" · {modalidad}" if modalidad else "")
                 + f" · del {texto.fmt_fecha(texto.fecha(curso.inicio), False, True)}"
                 f" al {texto.fmt_fecha(texto.fecha(curso.fin), False, True)}")
        l.append("")
        l.append("Copia local del material de Nexus hecha con `nexuscli clonar`. Cada carpeta tiene las "
                 "instrucciones de la actividad, su rúbrica y los recursos de su pestaña Recursos.")
        if self.man.get("comando"):
            l.append(f"Para actualizarla: `{self.man['comando']}`.")
        l.append("")
        l += ["- [Generales](generales/README.md): programa analítico, bienvenida, avisos y recursos que no son de "
              "una actividad.", ""]
        enc = "| Actividad | Evidencia | Cierra | Pts | Modalidad | Archivos | Enlaces | Rúbrica |"
        sep = "| --- | --- | --- | ---: | --- | ---: | ---: | --- |"
        if self.personal:
            enc = enc[:-1] + " Calificación |"
            sep += " ---: |"
        l += [enc, sep]
        for t, info in filas:
            c = info["carpeta"]
            celdas = [
                f"[{t.clave}]({liga_md(c)}/instrucciones.md)",
                t.nombre.replace("|", "\\|"),
                texto.fmt_fecha(t.cierre),
                f"{t.valor:g}" if t.valor is not None else "-",
                "equipo" if t.en_equipo else "individual",
                f"[{info['archivos']}]({liga_md(c)}/recursos.md)" if info["archivos"] else "0",
                str(info["enlaces"]),
                f"[sí]({liga_md(c)}/rubrica.md)" if info["rubrica"] else "no",
            ]
            if self.personal:
                celdas.append(f"{round(t.calificacion, 1):g}" if t.calificacion is not None else "-")
            l.append("| " + " | ".join(celdas) + " |")
        l.append("")
        self._escribir("README.md", "\n".join(l))


# ---------------------------------------------------------------------- helpers de render


def _plural(n: int, uno: str, varios: str | None = None) -> str:
    if not n:
        return ""
    return f"{n} {uno if n == 1 else (varios or uno + 's')}"


def _persona(p: dict) -> str:
    return " ".join(x for x in (p.get("Nombre"), p.get("ApellidoPaterno"), p.get("ApellidoMaterno")) if x).title()


def _id_recurso(clave: str, r: dict) -> tuple[str, int]:
    if clave == "RecursoArchivos":
        return ("doc", int((r.get("Documento") or {}).get("DocumentoId") or r.get("DocumentoId") or 0))
    for k in ("ExternoId", "TextoId", "HTMLId", "WebId", "LibroId", "ArticuloId", "ScormId", "RecursoId"):
        if r.get(k):
            return (k, int(r[k]))
    return ("?", hash(json.dumps(r, sort_keys=True, default=str)))


def _enlace(r: dict) -> str:
    url = (r.get("Contenido") or r.get("URL") or r.get("Url") or r.get("Liga") or r.get("Direccion") or "").strip()
    if url.startswith("<"):
        m = re.search(r'(?:src|href)="([^"]+)"', url)
        url = m.group(1) if m else ""
    titulo = arreglar_mojibake(texto.html_a_texto(r.get("Titulo") or r.get("Nombre") or "")).strip() or url or "enlace"
    desc = texto.html_a_texto(r.get("Descripcion") or "").strip()
    linea = f"[{titulo}]({url.replace(' ', '%20')})" if url else titulo
    if desc and desc != titulo:
        linea += f" · {texto.recortar(desc, 200)}"
    return linea


def _referencia(r: dict) -> str:
    campos = [r.get(k) for k in ("Autor", "Autores", "Titulo", "Nombre", "Editorial", "Revista", "Anio", "Año",
                                  "AnioPublicacion", "Paginas", "Edicion", "ISBN", "URL", "Url")]
    txt = ". ".join(str(c).strip() for c in campos if c not in (None, "", 0))
    return arreglar_mojibake(texto.html_a_texto(txt)) or json.dumps(
        {k: v for k, v in r.items() if isinstance(v, str) and v}, ensure_ascii=False)


def _niveles(rub: dict):
    niveles = sorted(rub.get("NivelDominios") or [], key=lambda n: n.get("Posicion") or 0)
    criterios = sorted((c for c in rub.get("Criterios") or [] if c.get("Estado", True)), key=lambda c: c.get("Posicion") or 0)
    celdas = {(c["CriterioId"], c["NivelDominioId"]): c for c in rub.get("CriterioNivelDominios") or []}
    return niveles, criterios, celdas


def _niveles_elegidos(rub: dict, seleccion: set[int]):
    niveles, criterios, celdas = _niveles(rub)
    for c in criterios:
        maximo = max((celdas.get((c["CriterioId"], n["NivelDominioId"]), {}).get("Puntos") or 0) for n in niveles) if niveles else 0
        elegido = next((n for n in niveles
                        if celdas.get((c["CriterioId"], n["NivelDominioId"]), {}).get("CriterioNivelDominioId") in seleccion), None)
        if elegido:
            pts = celdas[(c["CriterioId"], elegido["NivelDominioId"])].get("Puntos") or 0
            yield (c.get("Descripcion") or "").strip(), elegido.get("Nombre"), pts, maximo
        else:
            yield (c.get("Descripcion") or "").strip(), "-", 0, maximo


def _md_rubrica(t: Tarea, rub: dict, titulo: str, seleccion: set[int] | None) -> str:
    niveles, criterios, celdas = _niveles(rub)
    maximo_total = 0.0
    for c in criterios:
        maximo_total += max((celdas.get((c["CriterioId"], n["NivelDominioId"]), {}).get("Puntos") or 0) for n in niveles) if niveles else 0
    l = [f"# Rúbrica · {titulo}", ""]
    l.append(f"{_plural(len(criterios), 'criterio')} · niveles: {', '.join(n.get('Nombre') or '?' for n in niveles)}"
             f" · máximo {maximo_total:g} puntos")
    if seleccion:
        obtenido = sum(p for _c, _n, p, _m in _niveles_elegidos(rub, seleccion))
        pct = f" = {round(obtenido * 100 / maximo_total, 2):g} %" if maximo_total else ""
        l.append(f"\n**Obtuviste {obtenido:g} de {maximo_total:g}{pct}** (✓ marca el nivel que eligió el profesor).")
    l.append("")
    enc = "| Criterio | " + " | ".join(n.get("Nombre") or "?" for n in niveles) + " |"
    l += [enc, "| --- |" + " ---: |" * len(niveles)]
    for c in criterios:
        fila = [(c.get("Descripcion") or "").strip().replace("|", "\\|")]
        for n in niveles:
            celda = celdas.get((c["CriterioId"], n["NivelDominioId"])) or {}
            pts = celda.get("Puntos")
            txt = f"{pts:g}" if isinstance(pts, (int, float)) else "-"
            if seleccion and celda.get("CriterioNivelDominioId") in seleccion:
                txt = f"**{txt} ✓**"
            fila.append(txt)
        l.append("| " + " | ".join(fila) + " |")
    l.append("")
    for i, c in enumerate(criterios, 1):
        l += [f"## {i}. {(c.get('Descripcion') or '').strip()}", ""]
        for n in niveles:
            celda = celdas.get((c["CriterioId"], n["NivelDominioId"])) or {}
            pts = celda.get("Puntos")
            marca = " ✓" if seleccion and celda.get("CriterioNivelDominioId") in seleccion else ""
            desc = texto.html_a_texto(celda.get("Descripcion") or "").replace("\n", " ").strip() or "-"
            l.append(f"- **{n.get('Nombre')} · {pts:g}**{marca}: {desc}" if isinstance(pts, (int, float))
                     else f"- **{n.get('Nombre')}**{marca}: {desc}")
            retro = texto.html_a_texto(celda.get("Retralimentacion") or "").strip()
            if retro:
                l.append(f"  - Retroalimentación sugerida: {retro}")
        l.append("")
    return "\n".join(l)

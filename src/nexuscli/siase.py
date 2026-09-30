"""SIASE: AFIs con cupo, historial de AFIs, kardex, calificaciones y horario.

SIASE (deimos.dgi.uanl.mx) es Progress WebSpeed: páginas HTML en Latin-1, sin cookies. Después
del login, la página de carreras trae un campo oculto `HTMLtrim` que funciona como sesión (se
vence tras 30 minutos sin uso) y las claves de la carrera. Toda consulta es un GET a
`wspd_cgi.sh/<página>.htm` con esas claves en la URL; las que dependen de un periodo son un POST
a `control.p` con `HTMLTrund` y `HTMLResill` sacados de la página anterior.

Los errores llegan como un `alert('...')` en la página. Las funciones `parse_*` no hacen red:
reciben HTML y regresan datos, así se prueban con páginas de ejemplo.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from . import config, dom, texto
from .client import Client, NexusError

BASE = "https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/"
CLAVES = ("HTMLCve_Dependencia", "HTMLCve_Unidad", "HTMLCve_Nivel_Academico", "HTMLCve_Grado_Academico",
          "HTMLCve_Modalidad", "HTMLCve_Plan_Estudio", "HTMLCve_Carrera")
INACTIVIDAD = 25 * 60  # SIASE corta a los 30 min sin uso
_SESION_VENCIDA = re.compile(r"procedimiento restringido|inactividad|iniciar sesi[oó]n nuevamente", re.I)
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]


class SiaseError(NexusError):
    pass


class SesionVencida(SiaseError):
    pass


# ---------------------------------------------------------------------- datos


@dataclass
class Carrera:
    nombre: str
    claves: dict[str, str]
    usuario: str
    tipo: str = "01"


@dataclass
class Afi:
    id: int
    organizador: str
    area: str
    evento: str
    descripcion: str
    inicio: datetime | None
    fin: datetime | None
    capacidad: int | None
    registrados: int | None
    disponibles: int | None
    lleno: bool = False
    seleccionado: bool = False

    @property
    def con_cupo(self) -> bool:
        return not self.lleno and (self.disponibles or 0) > 0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["inicio"] = self.inicio.isoformat() if self.inicio else None
        d["fin"] = self.fin.isoformat() if self.fin else None
        d["con_cupo"] = self.con_cupo
        return d


@dataclass
class ListaAfis:
    afis: list[Afi]
    mes: int | None
    area: int | None
    areas: dict[int, str]
    meses: dict[int, str]
    html: str = field(default="", repr=False)


@dataclass
class EventoAfi:
    id: int
    evento: str
    area: str
    fecha: datetime | None
    asistencia: bool
    oficial: bool
    num_oficial: int
    periodo: str
    indicaciones: str = ""
    recinto: str = ""
    sede: str = ""
    direccion: str = ""
    municipio: str = ""
    estado: str = ""
    pais: str = ""
    organizador: str = ""
    descripcion: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["fecha"] = self.fecha.isoformat() if self.fecha else None
        return d


@dataclass
class HistorialAfis:
    oficiales: int
    requeridas: int
    eventos: list[EventoAfi]

    def ids(self) -> set[int]:
        return {e.id for e in self.eventos}


@dataclass
class MateriaKardex:
    semestre: str
    modalidad: str
    clave: str
    nombre: str
    oportunidades: list[str]
    laboratorio: str = ""

    @property
    def final(self) -> str:
        return next((o for o in reversed(self.oportunidades) if o), "")

    @property
    def aprobada(self) -> bool:
        return self.final.isdigit() and int(self.final) >= 70

    @property
    def cursada(self) -> bool:
        return any(self.oportunidades)

    @property
    def intentos(self) -> int:
        return sum(1 for o in self.oportunidades if o)


@dataclass
class Kardex:
    carrera: str
    plan: str
    materias: list[MateriaKardex]

    @property
    def promedio(self) -> float | None:
        notas = [int(m.final) for m in self.materias if m.aprobada]
        return round(sum(notas) / len(notas), 2) if notas else None


@dataclass
class Periodo:
    valor: str
    nombre: str


@dataclass
class Calificacion:
    clave: str
    materia: str
    tipo: str
    grupo: str
    fecha: str
    calificacion: str
    oportunidad: str


@dataclass
class MateriaHorario:
    tipo: str
    clave: str
    nombre: str
    abreviacion: str
    unidad: str
    grupo: str
    oferta: str
    frecuencia: str
    creditos: str
    oportunidad: str
    dependencia: str


@dataclass
class Bloque:
    dia: int          # 0 lunes ... 5 sábado
    inicio: str       # "07:00"
    fin: str          # "09:00"
    fase: str
    tipo: str
    abreviacion: str
    grupo: str
    salon: str


@dataclass
class Horario:
    periodo: str
    materias: list[MateriaHorario]
    bloques: list[Bloque]
    totales: dict[str, str]


@dataclass
class Perfil:
    matricula: str
    nombre: str
    carrera: str
    plan: str


# ---------------------------------------------------------------------- utilidades de parseo


def alertas(pagina: str) -> list[str]:
    """Mensajes de alert() que la página ejecuta al cargar (no los que están dentro de funciones)."""
    fuera = re.sub(r"function\s+\w+\s*\([^)]*\)\s*\{.*?\n\s*\}", " ", pagina, flags=re.S)
    return [dom.limpiar(m) for m in re.findall(r"alert\s*\(\s*['\"]([^'\"]+)['\"]", fuera)]


def revisar_sesion(pagina: str) -> None:
    for a in alertas(pagina):
        if _SESION_VENCIDA.search(a):
            raise SesionVencida(a)


def _entero(s: str) -> int | None:
    s = re.sub(r"[^\d-]", "", s or "")
    try:
        return int(s)
    except ValueError:
        return None


def fecha_siase(s: str) -> datetime | None:
    s = dom.limpiar(s)
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%d/%m/%y %H:%M", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _hora24(s: str) -> str:
    """'2:01 pm' -> '14:00' (SIASE marca cada bloque como h:01 a h+1:00)."""
    m = re.match(r"\s*(\d{1,2}):(\d{2})\s*([ap])\.?\s*m", s, re.I)
    if not m:
        return s.strip()
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ap == "p" and h != 12:
        h += 12
    if ap == "a" and h == 12:
        h = 0
    if mi == 1:
        mi = 0
    return f"{h:02d}:{mi:02d}"


def _opciones(sel: dom.Nodo | None) -> list[tuple[str, str]]:
    if sel is None:
        return []
    return [(o.attr("value"), o.texto()) for o in sel.todos("option")]


# ---------------------------------------------------------------------- parsers


def parse_login(pagina: str) -> tuple[str, list[Carrera]]:
    """La página eselcarrera.htm: HTMLtrim y una liga por carrera."""
    raiz = dom.parse(pagina)
    trim = raiz.primero("input", name="HTMLtrim")
    if trim is None or not trim.attr("value"):
        msgs = alertas(pagina)
        motivo = msgs[-1] if msgs else "SIASE no abrió la sesión (¿matrícula o contraseña incorrectas?)"
        raise SiaseError(motivo)
    carreras = []
    for a in raiz.todos("a"):
        href = a.attr("href")
        if "SelCarrera" not in href:
            continue
        valores = dict(re.findall(r"SelCarrera\.(HTML\w+)\.value\s*=\s*'([^']*)'", href))
        if not all(k in valores for k in CLAVES):
            continue
        carreras.append(Carrera(
            nombre=a.texto(), claves={k: valores[k] for k in CLAVES},
            usuario=valores.get("HTMLUsuCve", ""), tipo=valores.get("HTMLTipCve", "01"),
        ))
    if not carreras:
        raise SiaseError("SIASE no mostró ninguna carrera (revisa en tu dependencia la liberación de tu boleta)")
    return trim.attr("value"), carreras


def parse_perfil(pagina: str) -> Perfil:
    t = dom.parse(pagina).texto()

    def campo(etiqueta: str, siguiente: str) -> str:
        m = re.search(etiqueta + r"\s*:\s*(.+?)\s*(?:" + siguiente + r"|$)", t)
        return m.group(1).strip() if m else ""

    return Perfil(
        matricula=campo(r"Matr[ií]cula", r"Nombre"),
        nombre=campo(r"Nombre", r"Carrera|Escolar|$"),
        carrera=campo(r"Carrera", r"Plan de Estudios?"),
        plan=campo(r"Plan de Estudios?", r"Escolar|$"),
    )


def parse_afis(pagina: str) -> ListaAfis:
    raiz = dom.parse(pagina)
    tabla = raiz.primero("table", clase="TablaLink")
    if tabla is None:
        revisar_sesion(pagina)
        msgs = alertas(pagina)
        raise SiaseError(msgs[-1] if msgs else "SIASE no regresó la lista de AFIs")
    afis = []
    for fila in tabla.filas():
        cb = fila.primero("input", type="Checkbox") or fila.primero("input", type="checkbox")
        celdas = fila.celdas()
        if cb is None or len(celdas) < 9:
            continue
        evento = celdas[3]
        afis.append(Afi(
            id=int(cb.attr("value") or 0),
            organizador=celdas[1].texto(),
            area=celdas[2].texto(),
            evento=evento.texto(),
            descripcion=dom.limpiar(evento.attr("title")),
            inicio=fecha_siase(celdas[4].texto()),
            fin=fecha_siase(celdas[5].texto()),
            capacidad=_entero(celdas[6].texto()),
            registrados=_entero(celdas[7].texto()),
            disponibles=_entero(celdas[8].texto()),
            lleno="disabled" in cb.attrs,
            seleccionado="checked" in cb.attrs,
        ))
    areas = {int(v): n.title() for v, n in _opciones(raiz.primero("select", name="HTMLArea")) if v.isdigit()}
    meses: dict[int, str] = {}
    for v, n in _opciones(raiz.primero("select", name="HTMLMes")):
        if v.isdigit() and not n.startswith("-"):
            meses[int(v)] = n
    mes = raiz.primero("input", name="HTMLCveMes01")
    area = raiz.primero("input", name="HTMLCveArea01")
    return ListaAfis(
        afis=afis,
        mes=_entero(mes.attr("value")) if mes else None,
        area=_entero(area.attr("value")) if area else None,
        areas=areas, meses=meses, html=pagina,
    )


_ETIQUETAS_EVENTO = {
    "indicaciones": "indicaciones", "recinto": "recinto", "sede": "sede", "dirección": "direccion",
    "direccion": "direccion", "municipio": "municipio", "estado": "estado", "pais": "pais", "país": "pais",
    "organizado por": "organizador",
}


def _campos_evento(celda: dom.Nodo) -> dict[str, str]:
    """La celda "Evento" del historial: <b>3088 Evento:</b> nombre <br> <b>Recinto:</b> ...."""
    out: dict[str, str] = {}
    clave: str | None = None
    buf: list[str] = []

    def cerrar():
        if clave is not None:
            out[clave] = dom.limpiar(" ".join(buf))

    def walk(n: dom.Nodo):
        nonlocal clave, buf
        for h in n.hijos:
            if isinstance(h, str):
                buf.append(h)
            elif h.tag == "b":
                etiqueta = h.texto().rstrip(":").strip()
                m = re.match(r"(\d+)\s*Evento", etiqueta, re.I)
                if m:
                    cerrar()
                    out["id"] = m.group(1)
                    clave, buf = "evento", []
                    continue
                norm = texto.normalizar(etiqueta)
                encontrada = next((v for k, v in _ETIQUETAS_EVENTO.items() if texto.normalizar(k) == norm), None)
                if encontrada:
                    cerrar()
                    clave, buf = encontrada, []
                else:
                    buf.append(h.texto())
            elif h.tag == "br":
                buf.append(" ")
            else:
                walk(h)

    walk(celda)
    cerrar()
    return out


def parse_historial(pagina: str) -> HistorialAfis:
    raiz = dom.parse(pagina)
    t = raiz.texto()
    m_of = re.search(r"Asistencia Oficial\s*:\s*(\d+)", t)
    m_req = re.search(r"Valor AFI por Carrera\s*:\s*(\d+)", t)
    if not m_of:
        revisar_sesion(pagina)
        msgs = alertas(pagina)
        raise SiaseError(msgs[-1] if msgs else "SIASE no regresó el historial de AFIs")
    eventos = []
    tabla = next((tb for tb in raiz.todos("table") if "Evento Oficial" in (tb.filas()[0].texto() if tb.filas() else "")), None)
    for fila in (tabla.filas()[1:] if tabla else []):
        c = fila.celdas()
        if len(c) < 7:
            continue
        campos = _campos_evento(c[0])
        if "id" not in campos:
            continue
        eventos.append(EventoAfi(
            id=int(campos["id"]), evento=campos.get("evento", ""), area=c[1].texto(),
            fecha=fecha_siase(c[2].texto()), asistencia=c[3].texto().lower().startswith("s"),
            oficial=c[4].texto().lower().startswith("s"), num_oficial=_entero(c[5].texto()) or 0,
            periodo=c[6].texto(), descripcion=dom.limpiar(c[0].attr("title")),
            **{k: campos.get(k, "") for k in ("indicaciones", "recinto", "sede", "direccion", "municipio",
                                              "estado", "pais", "organizador")},
        ))
    return HistorialAfis(oficiales=int(m_of.group(1)), requeridas=int(m_req.group(1)) if m_req else 0, eventos=eventos)


def _tabla_con(raiz: dom.Nodo, *encabezados: str) -> dom.Nodo | None:
    for tb in raiz.todos("table"):
        fs = tb.filas()
        if fs and all(e.lower() in fs[0].texto().lower() for e in encabezados):
            return tb
    return None


def parse_kardex(pagina: str) -> Kardex:
    raiz = dom.parse(pagina)
    tabla = _tabla_con(raiz, "Materia", "Opo")
    if tabla is None:
        revisar_sesion(pagina)
        msgs = alertas(pagina)
        raise SiaseError(msgs[-1] if msgs else "SIASE no regresó el kardex")
    t = raiz.texto()
    carrera = re.search(r"Carrera\s*:\s*(.+?)\s*Plan de Estudio", t)
    plan = re.search(r"Plan de Estudio\s*:\s*(\S+)", t)
    materias = []
    for fila in tabla.filas()[1:]:
        c = [x.texto() for x in fila.celdas()]
        if len(c) < 10 or not c[3]:
            continue
        materias.append(MateriaKardex(
            semestre=c[0], modalidad=c[1], clave=c[2], nombre=c[3],
            oportunidades=(c[4:10] + [""] * 6)[:6], laboratorio=c[10] if len(c) > 10 else "",
        ))
    return Kardex(carrera=carrera.group(1) if carrera else "", plan=plan.group(1) if plan else "", materias=materias)


@dataclass
class FormularioPeriodo:
    accion: str
    campo: str
    resill: str
    periodos: list[Periodo]


def parse_periodos(pagina: str) -> FormularioPeriodo:
    raiz = dom.parse(pagina)
    sel = raiz.primero("select")
    form = raiz.primero("form")
    if sel is None or form is None:
        revisar_sesion(pagina)
        msgs = alertas(pagina)
        raise SiaseError(msgs[-1] if msgs else "SIASE no regresó los periodos")
    resill = raiz.primero("input", name="HTMLResill")
    return FormularioPeriodo(
        accion=form.attr("action").replace("&amp;", "&"),
        campo=sel.attr("name") or "HTMLPeriodo",
        resill=resill.attr("value") if resill else "",
        periodos=[Periodo(v, dom.limpiar(n)) for v, n in _opciones(sel) if v and v != "0"],
    )


def parse_calificaciones(pagina: str) -> tuple[str, list[Calificacion]]:
    raiz = dom.parse(pagina)
    tabla = _tabla_con(raiz, "Clave", "Materia", "Cfs")
    if tabla is None:
        revisar_sesion(pagina)
        msgs = alertas(pagina)
        raise SiaseError(msgs[-1] if msgs else "SIASE no regresó calificaciones")
    m = re.search(r"Periodo\s*:\s*(.+?)\s*(?:-->|Carrera|Consulta|Clave|$)", raiz.texto())
    out = []
    for fila in tabla.filas()[1:]:
        c = [x.texto() for x in fila.celdas()]
        if len(c) < 7 or not c[1]:
            continue
        out.append(Calificacion(clave=c[0], materia=c[1], tipo=c[2], grupo=c[3],
                                fecha="" if c[4] == "?" else c[4], calificacion=c[5], oportunidad=c[6]))
    return (m.group(1).strip() if m else ""), out


_CELDA_HORARIO = re.compile(r"(F-\d+)\s*/\s*(\w+)\s+(\S+)\s+(\S+)\s*/\s*(\S+)")


def parse_horario(pagina: str, periodo: str = "") -> Horario:
    raiz = dom.parse(pagina)
    grid = _tabla_con(raiz, "Lunes", "Martes")
    tabla_m = _tabla_con(raiz, "Clave Materia", "Abrevia")
    if grid is None or tabla_m is None:
        revisar_sesion(pagina)
        msgs = alertas(pagina)
        raise SiaseError(msgs[-1] if msgs else "SIASE no regresó el horario")
    materias = []
    for fila in tabla_m.filas()[1:]:
        c = [x.texto() for x in fila.celdas()]
        if len(c) < 13:
            continue
        materias.append(MateriaHorario(
            tipo=c[0], clave=c[1], nombre=c[2], abreviacion=c[3], unidad=c[4], grupo=c[5], oferta=c[6],
            frecuencia=f"{c[7]} presencial, {c[8]} en línea", creditos=c[10], oportunidad=c[11], dependencia=c[12],
        ))
    sueltos: list[Bloque] = []
    for fila in grid.filas()[1:]:
        c = fila.celdas()
        if len(c) < 2:
            continue
        horas = re.split(r"\s+a\s+", c[0].texto(), maxsplit=1)
        ini, fin = _hora24(horas[0]), _hora24(horas[-1])
        for dia, celda in enumerate(c[1:7]):
            m = _CELDA_HORARIO.search(celda.texto())
            if m:
                sueltos.append(Bloque(dia, ini, fin, m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)))
    # Une horas seguidas de la misma clase en un solo bloque.
    bloques: list[Bloque] = []
    for b in sorted(sueltos, key=lambda x: (x.dia, x.inicio)):
        prev = bloques[-1] if bloques else None
        if (prev and prev.dia == b.dia and prev.fin == b.inicio
                and (prev.abreviacion, prev.grupo, prev.salon, prev.fase) == (b.abreviacion, b.grupo, b.salon, b.fase)):
            prev.fin = b.fin
        else:
            bloques.append(Bloque(**asdict(b)))
    totales: dict[str, str] = {}
    tabla_t = _tabla_con(raiz, "Presenciales", "Totales")
    if tabla_t is not None and len(tabla_t.filas()) > 1:
        nombres = [x.texto() for x in tabla_t.filas()[0].celdas()]
        valores = [x.texto() for x in tabla_t.filas()[1].celdas()]
        totales = dict(zip(nombres, valores))
    return Horario(periodo=periodo, materias=materias, bloques=bloques, totales=totales)


def campos_formulario(pagina: str, nombre: str = "mi_forma", marcar: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Lo que un navegador enviaría al hacer submit del formulario: inputs (sin botones),
    selects con su opción elegida y checkboxes marcados (más los de `marcar`)."""
    raiz = dom.parse(pagina)
    form = raiz.primero("form", name=nombre) or raiz.primero("form")
    if form is None:
        return []
    marcar = marcar or {}
    campos: list[tuple[str, str]] = []
    for n in raiz.iterar():
        if n.tag not in ("input", "select", "textarea") or not n.attr("name"):
            continue
        tipo = n.attr("type").lower()
        nombre_c = n.attr("name")
        if n.tag == "select":
            ops = n.todos("option")
            elegida = next((o for o in ops if "selected" in o.attrs), ops[0] if ops else None)
            if elegida is not None:
                campos.append((nombre_c, elegida.attr("value")))
        elif tipo in ("button", "submit", "reset", "image", "file"):
            continue
        elif tipo in ("checkbox", "radio"):
            if "checked" in n.attrs or marcar.get(nombre_c) == n.attr("value"):
                campos.append((nombre_c, n.attr("value") or "on"))
        else:
            campos.append((nombre_c, n.attr("value")))
    return campos


# ---------------------------------------------------------------------- cliente


@dataclass
class SesionSiase:
    trim: str
    carrera: dict
    carreras: list[dict]
    ultimo_uso: float

    @property
    def vigente(self) -> bool:
        return bool(self.trim) and time.time() - self.ultimo_uso < INACTIVIDAD


class Siase:
    def __init__(self, client: Client, carrera: str | None = None) -> None:
        self.c = client
        self.consulta_carrera = carrera
        self._sesion: SesionSiase | None = None

    @property
    def path(self) -> Path:
        return self.c.state / "siase.json"

    # ------------------------------------------------------------------ sesión

    def sesion(self) -> SesionSiase:
        if self._sesion and self._sesion.vigente:
            return self._sesion
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            s = SesionSiase(**data)
            if s.vigente and self._carrera_ok(s):
                self._sesion = s
                return s
        except (FileNotFoundError, ValueError, TypeError):
            pass
        return self.login()

    def _carrera_ok(self, s: SesionSiase) -> bool:
        if not self.consulta_carrera:
            return True
        return texto.normalizar(self.consulta_carrera) in texto.normalizar(s.carrera.get("nombre", ""))

    def login(self) -> SesionSiase:
        pagina = self.c.entrar_siase()
        trim, carreras = parse_login(pagina)
        elegida = carreras[0]
        if self.consulta_carrera:
            q = texto.normalizar(self.consulta_carrera)
            hits = [c for c in carreras if q in texto.normalizar(c.nombre)]
            if not hits:
                raise SiaseError(f"Ninguna carrera coincide con {self.consulta_carrera!r}: "
                                 + "; ".join(c.nombre for c in carreras))
            elegida = hits[0]
        s = SesionSiase(trim=trim, carrera=asdict(elegida), carreras=[asdict(c) for c in carreras],
                        ultimo_uso=time.time())
        self._sesion = s
        self._guardar()
        return s

    def _guardar(self) -> None:
        if self._sesion:
            config.escribir_privado(self.path, json.dumps(asdict(self._sesion), ensure_ascii=False))

    def olvidar(self) -> None:
        self._sesion = None
        self.path.unlink(missing_ok=True)

    def params(self) -> dict[str, str]:
        s = self.sesion()
        car = s.carrera
        return {"HTMLUsuario": car["usuario"], "HTMLtrim": s.trim, **car["claves"], "HTMLTipCve": car.get("tipo", "01")}

    # ------------------------------------------------------------------ red

    def _pedir(self, metodo: str, url: str, *, params: dict | None = None, datos: Any = None, peso: float = 1.0) -> str:
        self.c.pacer.antes(peso)
        self.c._log(f"{metodo} {url.split('?')[0].rsplit('/', 1)[-1]}")
        headers = {"Referer": BASE + "default.htm", "Origin": "https://deimos.dgi.uanl.mx"}
        cuerpo = None
        if datos is not None:
            # Como el navegador: campos repetidos permitidos y codificados en el charset de la página.
            pares = list(datos.items()) if isinstance(datos, dict) else list(datos)
            cuerpo = urlencode(pares, encoding="latin-1", errors="replace")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            r = self.c.http.request(metodo, url, params=params, content=cuerpo, headers=headers)
        except Exception as e:  # httpx.HTTPError y compañía
            raise SiaseError(f"error de red con SIASE: {e}") from e
        finally:
            self.c.pacer.despues()
            self.c.llamadas += 1
        if r.status_code >= 400:
            raise SiaseError(f"SIASE respondió HTTP {r.status_code}")
        if self._sesion:
            self._sesion.ultimo_uso = time.time()
            self._guardar()
        return r.content.decode("latin-1")

    def consultar(self, pagina: str, parser: Callable[[str], Any], extra: dict | None = None) -> Any:
        """GET a una página con las claves de la sesión; si la sesión venció, entra y repite."""
        for intento in (1, 2):
            html_ = self._pedir("GET", BASE + pagina, params={**self.params(), **(extra or {})})
            try:
                revisar_sesion(html_)
                return parser(html_)
            except SesionVencida:
                if intento == 2:
                    raise
                self.olvidar()
                self.login()

    def _url(self, programa: str, extra: dict[str, str]) -> str:
        return BASE + programa + "?" + urlencode({**self.params(), **extra})

    # ------------------------------------------------------------------ consultas

    def perfil(self) -> Perfil:
        return self.consultar("maintop.htm", parse_perfil)

    def afis(self, mes: int | None = None, area: int | None = None) -> ListaAfis:
        extra: dict[str, str] = {}
        if mes:
            extra["HTMLCveMes"] = f"{mes:02d}"
        if area is not None:
            extra["HTMLCveArea"] = str(area)
        return self.consultar("delSavePrereg.htm", parse_afis, extra)

    def historial(self) -> HistorialAfis:
        return self.consultar("delConsRegEven.htm", parse_historial)

    def kardex(self) -> Kardex:
        return self.consultar("econkdx01.htm", parse_kardex)

    def _por_periodo(self, pagina: str, trund: str, periodo: str | None, parser: Callable[[str, str], Any]) -> Any:
        form: FormularioPeriodo = self.consultar(pagina, parse_periodos)
        p = elegir_periodo(form.periodos, periodo)
        html_ = self._pedir("POST", form.accion, datos={form.campo: p.valor, "HTMLTrund": trund, "HTMLResill": form.resill})
        revisar_sesion(html_)
        return parser(html_, p.nombre)

    def periodos(self) -> list[Periodo]:
        return self.consultar("econcfs01.htm", parse_periodos).periodos

    def calificaciones(self, periodo: str | None = None) -> tuple[str, list[Calificacion]]:
        def parser(h: str, nombre: str):
            p, cal = parse_calificaciones(h)
            return (nombre or p), cal
        return self._por_periodo("econcfs01.htm", "econcfs02", periodo, parser)

    def horario(self, periodo: str | None = None) -> Horario:
        h = self._por_periodo("echalm01.htm", "echalm02", periodo, lambda html_, n: parse_horario(html_, n))
        guardar_abreviaturas(self.c.state, h.materias)
        return h

    # ------------------------------------------------------------------ AFIs: escribir

    def preinscribir(self, afi_id: int, mes: int | None) -> dict:
        """Igual que en la web: marcar el evento (EventoA) recarga la lista con él seleccionado, y
        "Guardar Pre Registro" (GrabaReg) lo guarda en delSavePreReg20."""
        lista = self.afis(mes)
        afi = next((a for a in lista.afis if a.id == afi_id), None)
        if afi is None:
            raise SiaseError(f"La AFI {afi_id} no está en la lista de ese mes")
        if afi.lleno or not afi.con_cupo:
            raise SiaseError(f"La AFI {afi_id} ya no tiene cupo")
        if afi_id in self.historial().ids():
            raise SiaseError(f"Ya estás pre-registrado en la AFI {afi_id}")
        # 1. seleccionar
        campos = campos_formulario(lista.html, marcar={"Evento[]": str(afi_id)})
        sel = self._pedir("POST", self._url("delSavePrereg.htm", {"HTMLCveEvento": str(afi_id)}), datos=campos, peso=2)
        revisar_sesion(sel)
        if not re.search(r"GrabaReg\s*\(\s*'[^']+'\s*,\s*%d\s*\)" % afi_id, sel):
            raise SiaseError("SIASE no dejó seleccionar el evento: " + ("; ".join(alertas(sel)) or "sin mensaje"))
        programa = re.search(r"GrabaReg\s*\(\s*'([^']+)'\s*,\s*%d\s*\)" % afi_id, sel).group(1)
        # 2. guardar
        guardado = self._pedir("POST", self._url(programa, {"HTMLCveEvento": str(afi_id), "HTMLSaveDelReg": "0"}),
                               datos=campos_formulario(sel), peso=2)
        revisar_sesion(guardado)
        ok = afi_id in self.historial().ids()
        return {"afi": afi.as_dict(), "registrada": ok, "mensajes": alertas(guardado)}

    def liberar(self, afi_id: int) -> dict:
        """DelReg de la web: la misma petición que guarda, sobre un evento en el que ya estás."""
        hist = self.historial()
        ev = next((e for e in hist.eventos if e.id == afi_id), None)
        if ev is None:
            raise SiaseError(f"No estás pre-registrado en la AFI {afi_id}")
        if ev.asistencia:
            raise SiaseError(f"La AFI {afi_id} ya tiene tu asistencia registrada; no se libera")
        mes = ev.fecha.month if ev.fecha else None
        lista = self.afis(mes)
        guardado = self._pedir("POST", self._url("delSavePreReg20", {"HTMLCveEvento": str(afi_id), "HTMLSaveDelReg": "0"}),
                               datos=campos_formulario(lista.html), peso=2)
        revisar_sesion(guardado)
        ok = afi_id not in self.historial().ids()
        return {"afi": ev.as_dict(), "liberada": ok, "mensajes": alertas(guardado)}


def elegir_periodo(periodos: list[Periodo], consulta: str | None) -> Periodo:
    if not periodos:
        raise SiaseError("SIASE no tiene periodos para consultar")
    if not consulta:
        return periodos[0]
    q = texto.normalizar(consulta)
    if q.isdigit() and 1 <= int(q) <= len(periodos):
        return periodos[int(q) - 1]
    palabras = q.replace("-", " ").split()
    hits = [p for p in periodos if all(w in texto.normalizar(p.nombre).replace("-", " ") for w in palabras)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SiaseError(f"Ningún periodo coincide con {consulta!r}: " + "; ".join(p.nombre for p in periodos))
    return hits[0]


def mes_desde(texto_mes: str | None) -> int | None:
    if not texto_mes:
        return None
    t = texto.normalizar(texto_mes)
    if t.isdigit() and 1 <= int(t) <= 12:
        return int(t)
    for i, m in enumerate(_MESES, 1):
        if m.startswith(t[:3]):
            return i
    raise SiaseError(f"No entiendo el mes {texto_mes!r}")


def area_desde(consulta: str | None, areas: dict[int, str]) -> int | None:
    if not consulta:
        return None
    q = texto.normalizar(consulta)
    if q.isdigit():
        return int(q)
    hits = [k for k, v in areas.items() if texto.normalizar(v).startswith(q[:5])]
    if not hits:
        raise SiaseError(f"Ningún área coincide con {consulta!r}: " + ", ".join(areas.values()))
    return hits[0]


def dia_nombre(i: int) -> str:
    return _DIAS[i] if 0 <= i < len(_DIAS) else str(i)


# ---------------------------------------------------------------------- abreviaturas oficiales


def abreviaturas_path(state: Path) -> Path:
    return state / "siase-materias.json"


def guardar_abreviaturas(state: Path, materias: list[MateriaHorario]) -> None:
    datos = {texto.normalizar(m.nombre): m.abreviacion.lower() for m in materias if m.abreviacion}
    try:
        previos = json.loads(abreviaturas_path(state).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        previos = {}
    previos.update(datos)
    config.escribir_privado(abreviaturas_path(state), json.dumps(previos, ensure_ascii=False, indent=1))


def abreviatura_oficial(state: Path, nombre_curso: str) -> str | None:
    """La abreviatura de SIASE (CRNG, ANAU...) para una materia de Nexus, si ya se vio su horario."""
    try:
        datos: dict[str, str] = json.loads(abreviaturas_path(state).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    nombre = texto.normalizar(texto.curso_corto(nombre_curso))
    if nombre in datos:
        return datos[nombre]
    # SIASE recorta nombres largos; basta con que uno empiece con el otro.
    for k, v in datos.items():
        if len(k) >= 8 and (nombre.startswith(k) or k.startswith(nombre)):
            return v
    return None

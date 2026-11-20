"""Consultas escolares de SIASE: situación, inscripción, pagos, becas, trámites y datos.

Igual que en siase.py, cada `parse_*` recibe HTML y regresa datos, sin red. Salvo la evaluación
docente, son las opciones de solo lectura del menú de SIASE.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import dom
from .siase import (
    BASE, Siase, SiaseError, alertas, campos_formulario, parse_periodos, elegir_periodo, revisar_sesion,
)

DEYA = "https://deimos.dgi.uanl.mx/cgi-bin/deya.sh/"

PAGINAS = {
    "situacion": BASE + "ecSitEst01.htm",
    "fecha_inscripcion": BASE + "ecohoinsint01.htm",
    "adeudos": BASE + "ecavpag04.htm",
    "beca": BASE + "bccosobe01.htm",
    "encuestas": BASE + "eenc01.htm",
    "encuestas_docentes": BASE + "cemaenc01.htm",
    "tramites": BASE + "eccontram03.htm",
    "documentos": DEYA + "ecCargaDocto01.htm",
    "recibo": BASE + "ecBolRec-v02.htm",
    "recibo_intersemestral": BASE + "ecBolRec-v03.htm",
    "recibos_internos": BASE + "ecavpag01.htm",
    "datos": BASE + "edatal01.htm",
    "evaluaciones": BASE + "econeva01.htm",
}


def _lineas(pagina: str) -> str:
    return dom.parse(pagina).texto(saltos=True)


def _plano(pagina: str) -> str:
    return re.sub(r"\s+", " ", _lineas(pagina))


def _buscar(patron: str, texto_: str) -> str:
    m = re.search(patron, texto_, re.I)
    return m.group(1).strip() if m else ""


def _dinero(s: str) -> float | None:
    s = re.sub(r"[^\d.]", "", s or "")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _sin_datos(pagina: str, que: str) -> SiaseError:
    revisar_sesion(pagina)
    msgs = alertas(pagina)
    return SiaseError(msgs[-1] if msgs else f"SIASE no regresó {que}")


# ---------------------------------------------------------------------- parsers


@dataclass
class Situacion:
    semestre: str
    situacion: str
    tipo_inscripcion: str
    foto_aceptada: bool | None
    division: str


def parse_situacion(pagina: str) -> Situacion:
    t = _plano(pagina)
    situacion = _buscar(r"SITUACI[ÓO]N DEL ESTUDIANTE\s*:\s*(.+?)(?:\s+TIPO DE|$)", t)
    if not situacion:
        raise _sin_datos(pagina, "tu situación")
    foto = _buscar(r"FOTO ACEPTADA\s*:\s*(\w+)", t).upper()
    return Situacion(
        semestre=_buscar(r"SEMESTRE\s*:\s*(.+?)\s+ESTUDIANTE", t),
        situacion=situacion,
        tipo_inscripcion=_buscar(r"TIPO DE INSCRIPCI[ÓO]N\s*:\s*(.+?)(?:\s+FOTO|$)", t),
        foto_aceptada=True if foto.startswith("S") else (False if foto.startswith("N") else None),
        division=_buscar(r"Divisi[óo]n\s*:\s*-?\s*(.+?)(?:\s+SITUACI|$)", t),
    )


@dataclass
class FechaInscripcion:
    periodo: str
    dia: str
    hora: str


def parse_fecha_inscripcion(pagina: str) -> FechaInscripcion:
    lineas = _lineas(pagina).splitlines()
    t = " ".join(lineas)
    dia = _buscar(r"D[ií]a de Inscripci[óo]n\s*:\s*(.+?)(?:\s+Hora|$)", t)
    if not dia:
        raise _sin_datos(pagina, "tu fecha de inscripción")
    periodo = ""
    for i, ln in enumerate(lineas):
        if "Horario de Inscripci" in ln and i + 1 < len(lineas):
            periodo = lineas[i + 1]
    return FechaInscripcion(periodo=periodo, dia=dia, hora=_buscar(r"Hora de Inscripci[óo]n\s*:\s*(\S+)", t))


@dataclass
class Adeudo:
    cuenta: str
    cantidad: str
    concepto: str
    total: float | None


@dataclass
class Adeudos:
    fecha: str
    total: float
    conceptos: list[Adeudo]


def parse_adeudos(pagina: str) -> Adeudos:
    raiz = dom.parse(pagina)
    t = re.sub(r"\s+", " ", raiz.texto(saltos=True))
    m = re.search(r"Adeudo\s+Total\s*:\s*\$?\s*([\d,.]+)", t)
    if not m:
        raise _sin_datos(pagina, "tus adeudos")
    conceptos = []
    for tb in raiz.todos("table"):
        fs = tb.filas()
        if not fs or "Concepto" not in fs[0].texto():
            continue
        for f in fs[1:]:
            c = [x.texto() for x in f.celdas()]
            if len(c) >= 4 and c[2] and not c[0].lower().startswith("adeudo"):
                conceptos.append(Adeudo(cuenta=c[0], cantidad=c[1], concepto=c[2], total=_dinero(c[3])))
    return Adeudos(fecha=_buscar(r"Fecha\s*:\s*(\S+)", t), total=_dinero(m.group(1)) or 0.0, conceptos=conceptos)


@dataclass
class Beca:
    solicitud: bool
    mensaje: str


def parse_beca(pagina: str) -> Beca:
    lineas = [ln for ln in _lineas(pagina).splitlines() if ln and not ln.startswith("SIASE")]
    if not lineas:
        raise _sin_datos(pagina, "el resultado de beca")
    t = " ".join(lineas)
    if re.search(r"no cuenta con (una )?solicitud", t, re.I):
        return Beca(solicitud=False, mensaje=_buscar(r"(No cuenta con.+?)(?:$|\.)", t))
    despues = t.split("Cerrar", 1)[-1].strip()
    return Beca(solicitud=True, mensaje=despues or t)


def parse_encuestas(pagina: str) -> list[str]:
    raiz = dom.parse(pagina)
    if "Encuesta" not in raiz.texto():
        raise _sin_datos(pagina, "tus encuestas")
    return [o.texto() for o in raiz.todos("option") if o.attr("value") not in ("", "0") and o.texto()]


@dataclass
class EncuestaPendiente:
    valor: str = field(repr=False)
    nombre: str = ""


@dataclass
class ListaEncuestasDocentes:
    encuestas: list[EncuestaPendiente]
    accion: str = field(repr=False)
    resill: str = field(repr=False)


@dataclass
class OpcionEncuesta:
    texto: str
    valor: str = field(repr=False)


@dataclass
class PreguntaEncuesta:
    numero: int
    texto: str
    opciones: list[OpcionEncuesta]
    campo: str = field(repr=False)


@dataclass
class EncuestaDocente:
    nombre: str
    preguntas: list[PreguntaEncuesta]
    valor: str = field(repr=False)
    accion: str = field(repr=False)
    html: str = field(repr=False)

    def as_dict(self) -> dict:
        return {"nombre": self.nombre, "preguntas": [
            {"numero": p.numero, "pregunta": p.texto, "opciones": [o.texto for o in p.opciones]}
            for p in self.preguntas
        ]}


def parse_encuestas_docentes(pagina: str) -> ListaEncuestasDocentes:
    raiz = dom.parse(pagina)
    sel = raiz.primero("select", name="HTMLEncuesta")
    form = raiz.primero("form")
    resill = raiz.primero("input", name="HTMLResill")
    if sel is None or form is None or resill is None:
        raise _sin_datos(pagina, "tus encuestas docentes")
    encuestas = [EncuestaPendiente(o.attr("value"), o.texto()) for o in sel.todos("option")
                 if o.attr("value") and o.texto()]
    return ListaEncuestasDocentes(encuestas, form.attr("action"), resill.attr("value"))


def parse_encuesta_docente(pagina: str, pendiente: EncuestaPendiente) -> EncuestaDocente:
    raiz = dom.parse(pagina)
    radios = [n for n in raiz.iterar() if n.tag == "input" and n.attr("type").lower() == "radio"
              and n.attr("name")]
    grupos: dict[str, list[str]] = {}
    for radio in radios:
        grupos.setdefault(radio.attr("name"), []).append(radio.attr("value"))

    bloques: list[tuple[int, str, list[str]]] = []
    actual: tuple[int, str, list[str]] | None = None
    for linea in raiz.texto(saltos=True).splitlines():
        m = re.search(r"(\d+)\.-\s*(.+)", linea)
        if m:
            if actual:
                bloques.append(actual)
            actual = (int(m.group(1)), m.group(2), [])
        elif actual:
            actual[2].append(linea)
    if actual:
        bloques.append(actual)

    if not grupos or len(bloques) != len(grupos):
        raise _sin_datos(pagina, "las preguntas de la encuesta docente")
    preguntas = []
    for (numero, pregunta, opciones), (campo, valores) in zip(bloques, grupos.items()):
        if len(opciones) != len(valores):
            raise SiaseError(f"SIASE regresó {len(valores)} valores y {len(opciones)} respuestas para la pregunta {numero}")
        preguntas.append(PreguntaEncuesta(numero, pregunta,
                                          [OpcionEncuesta(t, v) for t, v in zip(opciones, valores)], campo))
    form = raiz.primero("form")
    if form is None:
        raise _sin_datos(pagina, "el formulario de la encuesta docente")
    return EncuestaDocente(pendiente.nombre, preguntas, pendiente.valor, form.attr("action"), pagina)


def elegir_opcion(pregunta: PreguntaEncuesta, consulta: str) -> OpcionEncuesta:
    from . import texto
    q = texto.normalizar(consulta)
    hits = [o for o in pregunta.opciones if texto.normalizar(o.texto) == q]
    if len(hits) != 1:
        raise SiaseError(f"Respuesta {consulta!r} inválida para la pregunta {pregunta.numero}: "
                         + ", ".join(o.texto for o in pregunta.opciones))
    return hits[0]


@dataclass
class Tramite:
    numero: str
    documento: str
    fecha: str
    importe: str
    estatus: str


@dataclass
class Tramites:
    tramites: list[Tramite]
    se_pueden_pedir: list[str]


def parse_tramites(pagina: str) -> Tramites:
    raiz = dom.parse(pagina)
    tabla = next((tb for tb in raiz.todos("table") if tb.filas() and "No. Solicitud" in tb.filas()[0].texto()), None)
    if tabla is None:
        raise _sin_datos(pagina, "tus trámites")
    tramites = []
    for f in tabla.filas()[1:]:
        c = [x.texto() for x in f.celdas()]
        if len(c) >= 5 and c[0]:
            tramites.append(Tramite(numero=c[0], documento=c[1], fecha=c[2], importe=c[3], estatus=c[4]))
    sel = raiz.primero("select")
    tipos = [o.texto() for o in (sel.todos("option") if sel else []) if o.attr("value") not in ("", "0")]
    return Tramites(tramites=tramites, se_pueden_pedir=tipos)


@dataclass
class Documentos:
    estado: str
    pendientes: list[str]


def parse_documentos(pagina: str) -> Documentos:
    lineas = [ln for ln in _lineas(pagina).splitlines() if ln]
    try:
        i = next(k for k, ln in enumerate(lineas) if "Entrega de documentos" in ln)
    except StopIteration:
        raise _sin_datos(pagina, "tus documentos") from None
    resto = lineas[i + 1:]
    if not resto:
        return Documentos(estado="sin información", pendientes=[])
    return Documentos(estado=resto[0], pendientes=resto[1:])


@dataclass
class Concepto:
    cuenta: str
    concepto: str
    importe: float | None


@dataclass
class Recibo:
    periodo: str
    inscripcion: str
    conceptos: list[Concepto]
    total: float | None
    pagado: bool
    fecha_limite: str
    pago_fecha: str = ""
    pago_monto: float | None = None
    pago_estado: str = ""


def parse_recibo(pagina: str) -> Recibo:
    raiz = dom.parse(pagina)
    lineas = raiz.texto(saltos=True)
    if "Recibo de Servicios" not in lineas:
        raise _sin_datos(pagina, "un recibo")
    conceptos = []
    total = None
    for f in raiz.todos("tr"):
        c = [x.texto() for x in f.celdas()]
        if len(c) >= 3 and re.fullmatch(r"\d{4}", c[0]):
            conceptos.append(Concepto(cuenta=c[0], concepto=c[1], importe=_dinero(c[2])))
        elif c and any("TOTAL" in x for x in c) and len(c) >= 2:
            total = _dinero(c[-1])
    plano = re.sub(r"\s+", " ", lineas)
    return Recibo(
        periodo=_buscar(r"PERIODO DE INSCRIPCI[ÓO]N:\s*\n?(.+)", lineas),
        inscripcion=_buscar(r"\nINSCRIPCI[ÓO]N\n(.+)", lineas),
        conceptos=conceptos, total=total,
        pagado=bool(re.search(r"Recibo Pagado|ya ha sido pagad", plano + " " + " ".join(alertas(pagina)), re.I)),
        fecha_limite=_buscar(r"antes del (.+?)(?:\s+Tr[áa]mite|\s*$)", plano),
        pago_fecha=_buscar(r"Monto pagado:.*?Fecha:\s*(\d{2}/\d{2}/\d{4})", plano),
        pago_monto=_dinero(_buscar(r"Monto pagado:\s*\$?\s*([\d,.]+)", plano)),
        pago_estado=_buscar(r"Transacci[óo]n:\s*(\w+)", plano),
    )


@dataclass
class ReciboInterno:
    id: str
    nombre: str
    estado: str


def parse_recibos_internos(pagina: str) -> list[ReciboInterno]:
    raiz = dom.parse(pagina)
    if "Recibo Interno" not in raiz.texto():
        raise _sin_datos(pagina, "tus recibos internos")
    out = []
    estado = ""
    for n in raiz.iterar():
        if n.tag in ("td", "th", "p", "div", "span", "b", "font", "h3", "h4") and re.match(r"Boletas\s+\w+", n.texto()) \
                and len(n.texto()) < 40:
            estado = n.texto().replace("Boletas", "").strip()
        if n.tag == "a":
            m = re.search(r"ejecuta\('([^']+)'\)", n.attr("href"))
            if m:
                out.append(ReciboInterno(id=m.group(1), nombre=n.texto(), estado=estado))
    return out


@dataclass
class SeccionDatos:
    titulo: str
    campos: list[tuple[str, str]] = field(default_factory=list)


def parse_datos(pagina: str) -> list[SeccionDatos]:
    raiz = dom.parse(pagina)
    if "Datos Personales" not in raiz.texto():
        raise _sin_datos(pagina, "tus datos personales")
    secciones: list[SeccionDatos] = []
    vistas: set[str] = set()
    for f in raiz.todos("tr"):
        c = [x.texto() for x in f.celdas()]
        if not any(c):
            continue
        if len(c) == 1:
            titulo = c[0]
            if titulo in vistas or titulo.startswith("Datos Personales del"):
                continue
            vistas.add(titulo)
            secciones.append(SeccionDatos(titulo))
            continue
        if not secciones:
            secciones.append(SeccionDatos("Datos"))
        for i in range(0, len(c) - 1, 2):
            etiqueta, valor = c[i].rstrip(": ").strip(), c[i + 1]
            if etiqueta and valor:
                secciones[-1].campos.append((etiqueta, valor))
    return [s for s in secciones if s.campos]


def tablas(pagina: str) -> list[dict]:
    """Tablas genéricas (encabezado + filas), para páginas cuyo formato cambia por periodo."""
    out = []
    for tb in dom.parse(pagina).todos("table"):
        fs = tb.filas()
        if len(fs) < 2:
            continue
        enc = [c.texto() for c in fs[0].celdas()]
        if sum(1 for e in enc if e) < 2:
            continue
        filas = [[c.texto() for c in f.celdas()] for f in fs[1:]]
        filas = [f for f in filas if any(f)]
        if filas:
            out.append({"encabezados": enc, "filas": filas})
    return out


# ---------------------------------------------------------------------- consultas


class Escolar:
    """Las consultas del menú de SIASE sobre una sesión de `Siase`."""

    def __init__(self, s: Siase) -> None:
        self.s = s

    def situacion(self) -> Situacion:
        return self.s.consultar(PAGINAS["situacion"], parse_situacion)

    def fecha_inscripcion(self) -> FechaInscripcion:
        return self.s.consultar(PAGINAS["fecha_inscripcion"], parse_fecha_inscripcion)

    def adeudos(self) -> Adeudos:
        return self.s.consultar(PAGINAS["adeudos"], parse_adeudos)

    def beca(self) -> Beca:
        return self.s.consultar(PAGINAS["beca"], parse_beca)

    def encuestas(self) -> list[str]:
        generales = self.s.consultar(PAGINAS["encuestas"], parse_encuestas)
        return generales + [e.nombre for e in self.encuestas_docentes().encuestas]

    def encuestas_docentes(self) -> ListaEncuestasDocentes:
        return self.s.consultar(PAGINAS["encuestas_docentes"], parse_encuestas_docentes)

    def encuesta_docente(self, consulta: str) -> EncuestaDocente:
        from . import texto
        lista = self.encuestas_docentes()
        palabras = texto.normalizar(consulta).split()
        hits = [e for e in lista.encuestas
                if all(p in texto.normalizar(e.nombre) for p in palabras)]
        if len(hits) != 1:
            nombres = "; ".join(e.nombre for e in (hits or lista.encuestas))
            motivo = "Varias encuestas coinciden" if hits else "Ninguna encuesta coincide"
            raise SiaseError(f"{motivo} con {consulta!r}: {nombres or 'no hay encuestas docentes pendientes'}")
        pendiente = hits[0]
        pagina = self.s._pedir("POST", lista.accion, datos={"HTMLEncuesta": pendiente.valor,
                                                            "HTMLTrund": "cemaenc01",
                                                            "HTMLResill": lista.resill})
        revisar_sesion(pagina)
        return parse_encuesta_docente(pagina, pendiente)

    def contestar_encuesta(self, encuesta: EncuestaDocente,
                           respuestas: dict[int, OpcionEncuesta]) -> dict:
        campos_elegidos = {}
        for pregunta in encuesta.preguntas:
            opcion = respuestas.get(pregunta.numero)
            if opcion is None or opcion.valor not in {o.valor for o in pregunta.opciones}:
                raise SiaseError(f"Falta una respuesta válida para la pregunta {pregunta.numero}")
            campos_elegidos[pregunta.campo] = opcion.valor
        campos = campos_formulario(encuesta.html, marcar=campos_elegidos)
        campos = [(nombre, "cemaenc20" if nombre == "HTMLTrund" else valor) for nombre, valor in campos]
        pagina = self.s._pedir("POST", encuesta.accion, datos=campos, peso=2)
        revisar_sesion(pagina)
        pendiente = any(e.valor == encuesta.valor for e in self.encuestas_docentes().encuestas)
        return {
            "encuesta": encuesta.nombre,
            "contestada": not pendiente,
            "respuestas": [{"numero": p.numero, "pregunta": p.texto,
                            "respuesta": respuestas[p.numero].texto} for p in encuesta.preguntas],
            "mensajes": alertas(pagina),
        }

    def tramites(self) -> Tramites:
        return self.s.consultar(PAGINAS["tramites"], parse_tramites)

    def documentos(self) -> Documentos:
        return self.s.consultar(PAGINAS["documentos"], parse_documentos)

    def recibo(self, intersemestral: bool = False) -> Recibo:
        return self.s.consultar(PAGINAS["recibo_intersemestral" if intersemestral else "recibo"], parse_recibo)

    def recibos_internos(self) -> list[ReciboInterno]:
        return self.s.consultar(PAGINAS["recibos_internos"], parse_recibos_internos)

    def datos(self) -> list[SeccionDatos]:
        return self.s.consultar(PAGINAS["datos"], parse_datos)

    def evaluaciones(self, periodo: str | None = None) -> tuple[str, list[dict], str]:
        """Evaluaciones parciales: (periodo, tablas, mensaje de SIASE si no hay)."""
        form = self.s.consultar(PAGINAS["evaluaciones"], parse_periodos)
        p = elegir_periodo(form.periodos, periodo)
        pagina = self.s._pedir("POST", form.accion, datos={form.campo: p.valor, "HTMLTrund": "econeva02",
                                                         "HTMLResill": form.resill})
        revisar_sesion(pagina)
        msgs = alertas(pagina)
        return p.nombre, tablas(pagina), (msgs[-1] if msgs else "")

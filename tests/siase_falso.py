"""Un SIASE de mentira: páginas con la misma estructura que las reales y datos inventados.

Lo usan los tests y las capturas del README. Las páginas copian las rarezas de SIASE
(etiquetas en mayúsculas, <font>, celdas sin cerrar, descripción en el title, alert() dentro
de funciones) para que los parsers se prueben contra algo parecido a lo real. Guarda estado:
pre-registrarse o liberar cambia el historial igual que en SIASE, donde la misma petición
alterna el registro.
"""

from __future__ import annotations

import html
from copy import deepcopy
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import httpx

TRIM = "90817263"
CLAVES = {"HTMLCve_Dependencia": "09999", "HTMLCve_Unidad": "01", "HTMLCve_Nivel_Academico": "02",
          "HTMLCve_Grado_Academico": "03", "HTMLCve_Modalidad": "4", "HTMLCve_Plan_Estudio": "430",
          "HTMLCve_Carrera": "02"}
MATRICULA = "1234567"


@dataclass
class AfiFalsa:
    id: int
    organizador: str
    area: str
    evento: str
    descripcion: str
    inicio: str      # "30/09/2026 11:00"
    fin: str
    capacidad: int
    registrados: int

    @property
    def disponibles(self) -> int:
        return max(self.capacidad - self.registrados, 0)


@dataclass
class EventoFalso:
    id: int
    evento: str
    area: str
    fecha: str
    asistencia: bool
    oficial: bool
    num: int
    periodo: str
    recinto: str = "Aula Magna del Colegio Civil"
    sede: str = "Colegio Civil"
    direccion: str = "Colegio Civil s/n, Centro"
    indicaciones: str = "Registra tu asistencia en el módulo AFI."


AFIS = [
    AfiFalsa(4101, "DIRECCION DE DESARROLLO CULTURAL", "CULTURALES", "Ciclo de cine: Poéticas del espacio",
             "Proyección y charla con la curaduría del cineclub.", "07/10/2026 18:00", "07/10/2026 20:00", 50, 50),
    AfiFalsa(4102, "DIRECCION DE DESARROLLO CULTURAL", "ARTISTICAS", "Muestra de danza folklórica UANL",
             "Presentación de los grupos representativos de danza.", "09/10/2026 11:00", "09/10/2026 13:00", 500, 118),
    AfiFalsa(4103, "FACULTAD DE ARTES VISUALES", "ACADEMICAS", "Masterclass: sonido para cine independiente",
             "Sonidistas de la industria hablan de grabación en locación y diseño sonoro.",
             "12/10/2026 10:00", "12/10/2026 12:00", 120, 112),
    AfiFalsa(4104, "FACULTAD DE ARTES VISUALES", "DEPORTIVAS", "Torneo intrauniversitario de voleibol mixto",
             "Tres entrenamientos por semana y el día de la competencia.", "10/09/2026 16:30", "15/11/2026 18:30", 20, 7),
    AfiFalsa(4105, "CENTRO UNIVERSITARIO DE SALUD", "RESPONSABILIDAD SOCIAL", "Taller: ansiedad y procrastinación",
             "Estrategias para organizar el semestre.", "14/10/2026 13:00", "14/10/2026 14:00", 9999, 1052),
    AfiFalsa(4106, "DIRECCION DE ACTIVIDADES ESTUDIANTILES", "INNOVACION Y EMPRENDIMIENTO",
             "UANL IT Summit: bloque de diseño", "Charlas de diseño de producto y portafolio.",
             "20/10/2026 10:00", "20/10/2026 14:00", 300, 180),
    AfiFalsa(4107, "FACULTAD DE ARQUITECTURA", "ARTISTICAS", "Taller de acuarela y técnicas de registro",
             "Cuatro sesiones los sábados.", "03/10/2026 09:00", "31/10/2026 13:00", 15, 13),
    AfiFalsa(4108, "FACULTAD DE FILOSOFIA Y LETRAS", "CULTURALES", "Presentación de libro: la ciudad y sus imágenes",
             "Con la autora y comentaristas invitados.", "22/10/2026 19:00", "22/10/2026 20:30", 40, 40),
]

HISTORIAL = [
    EventoFalso(5201, "Obra de teatro: la casa de los espejos", "CULTURALES", "27/08/2025 20:00", True, True, 2,
                "Agosto-Diciembre 2025"),
    EventoFalso(5202, "Charla con artista invitada", "ACADEMICAS", "02/09/2025 10:00", True, True, 1,
                "Agosto-Diciembre 2025"),
    EventoFalso(5203, "Recorrido guiado por exposición", "CULTURALES", "05/09/2025 13:00", True, True, 3,
                "Agosto-Diciembre 2025"),
    EventoFalso(5204, "Congreso de innovación: día 2", "INNOVACION Y EMPRENDIMIENTO", "11/09/2025 10:00", False, False, 0,
                "Agosto-Diciembre 2025"),
    EventoFalso(5205, "Conferencia: ríos urbanos", "RESPONSABILIDAD SOCIAL", "21/03/2024 12:00", True, True, 1,
                "ENERO-JUNIO 2024"),
]

KARDEX = [
    ("1", "1", "101", "Cultura de paz", ["58", "NC", "82"]),
    ("1", "1", "102", "Ética y cultura de la legalidad", ["93"]),
    ("1", "1", "103", "Lenguaje visual", ["81"]),
    ("2", "1", "201", "Lenguaje audiovisual", ["90"]),
    ("2", "1", "202", "Antropología visual", ["87"]),
    ("3", "1", "301", "Guion cinematográfico", ["64"]),
    ("3", "1", "302", "Sonido", ["79"]),
    ("4", "1", "401", "Semiótica de la imagen", []),
    ("4", "1", "402", "Iluminación y fotometría", []),
]

PERIODOS = [("0x00000000003b9471", "Semestral Agosto-Diciembre 2026"),
            ("0x00000000003b9101", "Semestral Enero - Junio 2026")]

CALIFICACIONES = {
    "0x00000000003b9101": [("202", "Antropología visual", "CO", "211", "22/05/26", "87", "1"),
                           ("302", "Sonido", "CO", "212", "19/05/26", "79", "1"),
                           ("301", "Guion cinematográfico", "CO", "213", "21/05/26", "64", "1")],
    "0x00000000003b9471": [("301", "Guion cinematográfico", "CO", "313", "?", "", "2"),
                           ("401", "Semiótica de la imagen", "CO", "201", "?", "", "1"),
                           ("402", "Iluminación y fotometría", "CO", "214", "?", "", "1")],
}

MATERIAS_HORARIO = [
    ("CO", "301", "Guion cinematográfico", "GUCI", "313", "Mixta", "2", "1", "3", "3", "2"),
    ("CO", "401", "Semiótica de la imagen", "SEIM", "201", "Escolarizada", "4", "0", "4", "4", "1"),
    ("CO", "402", "Iluminación y fotometría", "ILFO", "214", "Escolarizada", "3", "0", "3", "4", "1"),
    ("CO", "403", "Montaje", "MONT", "215", "No Escolarizada", "0", "3", "3", "3", "1"),
]
# (día 0-5, hora de inicio 24h, horas, abreviación, grupo, salón)
BLOQUES = [(0, 8, 2, "SEIM", "201", "A105"), (1, 12, 3, "ILFO", "214", "SET2"), (2, 16, 2, "GUCI", "313", "C104"),
           (3, 8, 2, "SEIM", "201", "A105")]


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _base_qs() -> str:
    return f"HTMLUsuario={MATRICULA}&HTMLtrim={TRIM}&" + "&".join(f"{k}={v}" for k, v in CLAVES.items()) + "&HTMLTipCve=01"


# ---------------------------------------------------------------------- páginas


def pagina_login() -> str:
    asignaciones = ";\n".join(f"self.document.SelCarrera.{k}.value='{v}'" for k, v in CLAVES.items())
    return f"""<HTML><HEAD><TITLE>SIASE</TITLE></HEAD><BODY>
<FORM name="SelCarrera" ACTION="default.htm" METHOD="post" TARGET="_self">
<p class="barra">Listado de Carreras</p>
 <a href="javascript:{asignaciones};
   self.document.SelCarrera.HTMLTipCve.value='01';
   self.document.SelCarrera.HTMLUsuCve.value='{MATRICULA}';
   self.document.SelCarrera.submit()"><p>FACULTAD DE ARTES VISUALES - LIC. EN LENG. Y PROD. AUDIOVISUAL 430-02</p></a>
<input type="hidden" name="HTMLtrim" value="{TRIM}">
</FORM>
<form name="frNexus" id="idfrNexus" method="GET" target="_new"></form>
<script>$("#idfrNexus").attr("action", "https://plataformanexus.uanl.mx/#/LoginSIASE?Usu=0x0&Ctrl=abc&HTMLUsuario={MATRICULA}&HTMLTipCve=01");</script>
</BODY></HTML>"""


def pagina_error(mensaje: str) -> str:
    return f"<HTML><BODY><SCRIPT LANGUAGE='JavaScript'>alert('{mensaje}');</SCRIPT></BODY></HTML>"


def pagina_perfil() -> str:
    return f"""<HTML><BODY><TABLE><TR><TD></TD><TD><span class="style1">Matrícula : {MATRICULA}
Nombre : ANA LOPEZ GARZA Carrera : LIC. EN LENG. Y PROD. AUDIOVISUAL 430-02 Plan de Estudios : Modelo Academico 2020</span>
</TD></TR></TABLE><TABLE><TR><TD>Escolar</TD><TD>Tesoreria</TD><TD>AFI</TD></TR></TABLE></BODY></HTML>"""


_AREAS = ["Todas", "ACADEMICAS", "INVESTIGACION", "CULTURALES", "ARTISTICAS", "DEPORTIVAS", "APRENDIZAJE DE IDIOMAS",
          "RESPONSABILIDAD SOCIAL", "INTERCAMBIO ACADEMICO", "INNOVACION Y EMPRENDIMIENTO", "INSTITUCIONAL"]
_MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
          "Noviembre", "Diciembre"]


def pagina_afis(afis: list[AfiFalsa], mes: int, area: int = 0, seleccion: int = 0, registradas: set[int] = frozenset()) -> str:
    filas = []
    for i, a in enumerate(afis):
        color = "#eeefe7" if i % 2 == 0 else "#ffffff"
        if a.disponibles == 0:
            cb = (f'<td align="center" title="Dar click para liberar el evento"> <font size="1"> <input type="Checkbox" '
                  f'disabled readonly id="Evento{a.id}" name="Evento[]" value="{a.id}" onclick="DelReg(\'delSavePreReg20\', {a.id})"> </font> </td>')
        else:
            marcado = " checked" if a.id == seleccion else ""
            cb = (f'<td align="center"> <font size="1"> <input type="Checkbox"{marcado} id="Evento{a.id}" name="Evento[]" '
                  f'value="{a.id}" onclick="EventoA(\'delSavePrereg.htm\', {a.id})"> </font> </td>')
        celda = lambda t: f'<td align="left" ><font face="Arial" size="1" color="#003366">{_e(t)}</font></td>'
        filas.append(f"""<tr bgcolor="{color}"> {cb}
 {celda(a.organizador)} {celda(a.area)}
 <td align="left" title="{_e(a.descripcion)}"><font face="Arial" size="1" color="#003366">{_e(a.evento)}</font></td>
 <td align="center"><font face="Arial" size="1" color="#003366">{a.inicio}</font></td>
 <td align="center"><font face="Arial" size="1" color="#003366">{a.fin}</font></td>
 <td align="center"><font face="Arial" size="1" color="#003366">{a.capacidad}</font></td>
 <td align="center"><font face="Arial" size="1" color="#003366">{a.registrados}</font></td>
 <td align="center"><font face="Arial" size="1" color="#003366">{a.disponibles}</font></td>
 <td align="center"><font face="arial" color="#003366"></td> </tr>
 <script language="javascript"> $("#BtnReg").show(); </script>""")
    enc = "".join(f'<td align="middle" bgcolor="#FFEA96"><div align="center"><p align="center"><font face="Arial" size="2">'
                  f'<b>{t}</b></font></div></td>' for t in ["", "Organizado por", "Area", "Evento", "Fecha y Hora Incia",
                                                             "Fecha y Hora Termina", "Capacidad", "Pre-Registro",
                                                             "Disponibles", "Eliminar Evento"])
    ops_area = "".join(f'<option value="{i}" {"selected" if i == area else ""}>{n}</option>' for i, n in enumerate(_AREAS))
    ops_mes = f'<option value="{mes}">--> {_MESES[mes - 1]}</option>' + "".join(
        f'<option value="{i:02d}">{n}</option>' for i, n in enumerate(_MESES, 1))
    boton = f"GrabaReg('delSavePreReg20',{seleccion})"
    return f"""<html><head><script>
function EventosxArea(vcPrograma,vinCveArea,vinCveMes) {{
 document.mi_forma.action='https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/'+vcPrograma+'?{_base_qs()}'+"&HTMLCveArea="+vinCveArea;
 document.mi_forma.submit();
}}
function EventoA(vcPrograma,vinNoConv) {{
 var vchecado = $("#Evento" + vinNoConv).prop('checked');
 if (vchecado == false ) {{
 alert("No ha seleccionado un evento...");
 return;
 }}
 document.mi_forma.submit();
}}
function GrabaReg(vcPrograma,vinEvento) {{
 if (vinEvento == 0 ) {{
 alert("No ha seleccionado un evento...");
 return;
 }}
 document.mi_forma.submit();
}}
</script></head><body>
<form method="POST" action="https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/control.p?{_base_qs()}" name="mi_forma" border="0">
<input name="HTMLCveEvento01" id="CveEvento" type="hidden" value="{seleccion}">
<input name="HTMLCveArea01" id="CveArea01" type="hidden" value="{area}">
<input name="HTMLCveMes01" id="CveMes01" type="hidden" value="{mes}">
<input name="HTMLEc_Inscripcion" type="hidden" value="0x0000000000abc123">
<table WIDTH="95%"><tr><td>&nbsp;</td></tr>
<td width="30%"><span class="style4">Area </span> <select id="Areas" name="HTMLArea" >{ops_area}</select>
<td><span class="style4">Mes </span> <select id="Meses" name="HTMLMes">{ops_mes}</select>
</table>
<table class="TablaLink" width="100%"><tr> {enc} </tr>
{"".join(filas)}
</table>
<table><tr><td>Descripción del evento</td></tr></table>
<div id="BtnReg"><input type="button" id="Continuar" name="Continuar" value="Guardar Pre Registro" onclick="{boton}"></div>
<input type="hidden" name="HTMLTrund" value="">
<input name="HTMLResill" type="hidden" value="40001">
<input name="HTMLFecha_Cita" type="hidden" value="08/10/2026">
</form></body></html>"""


def pagina_historial(eventos: list[EventoFalso], oficiales: int, requeridas: int = 14) -> str:
    filas = []
    for e in eventos:
        filas.append(f"""<tr > <td align="left" bgcolor="#FDFEFE" title="Descripción de {_e(e.evento)}"><font face="Arial" size="1" color="#003366">
 <b>{e.id}   Evento:</b> {_e(e.evento)} <br> <b> Indicaciones: </b> {_e(e.indicaciones)} <br>
 <b> Recinto: </b> {_e(e.recinto)}<br> <b> Sede: </b> {_e(e.sede)}<br> <b> Dirección: </b> {_e(e.direccion)}<br>
 <b> Municipio: </b> MONTERREY<br> <b> Estado: </b> NUEVO LEON<br> <b> Pais: </b> MEXICO<br>
 <b> Organizado por: </b> DIRECCION DE DESARROLLO CULTURAL</font></td>
 <td align="center"><font size="1">{e.area}</font></td>
 <td align="center"><font size="1">{e.fecha}</font></td>
 <td align="center"><font size="1">{"Si" if e.asistencia else "No"}</font></td>
 <td align="center"><font size="1">{"Si" if e.oficial else "No"}</font></td>
 <td align="center"><font size="1">{e.num}</font></td>
 <td align="center"><font size="1">{e.periodo}</font></td></tr>""")
    enc = "".join(f'<td align="middle" bgcolor="#FFEA96"><b>{t}</b></td>' for t in
                  ["Evento", "Area", "Fecha Evento ", " Asistencia ", "Evento Oficial", "# Evento Oficial ", "Periodo Esc."])
    return f"""<html><body><script>function x(){{ alert("Periodo_Escolar.Cve_Periodo: 999"); }}</script>
<table></table><table></table>
<table><tr><td>Total de AFI's con Asistencia Oficial: {oficiales}</td><td>Valor AFI por Carrera: {requeridas}</td></tr></table>
<table class="TablaLink"><tr>{enc}</tr>{"".join(filas)}</table><table></table></body></html>"""


def pagina_kardex() -> str:
    filas = []
    for sem, mod, clave, nombre, ops in KARDEX:
        celdas = "".join(f"<TD>{o}</TD>" for o in (ops + [""] * 6)[:6])
        filas.append(f"<TR><TD>{sem}<TD>{mod}<TD>{clave}<TD>{_e(nombre)}{celdas}<TD></TR>")
    enc = "".join(f"<TD><b>{t}</b></TD>" for t in ["Sem.", "Mod.", "Clave", "Materia", "1 Opo.", "2 Opo.", "3 Opo.",
                                                    "4 Opo", "5 Opo", "6 Opo", "Labs."])
    return f"""<HTML><BODY><TABLE><TR><TD>Carrera : LIC. EN LENG. Y PROD. AUDIOVISUAL 430-02</TD><TD>Plan de Estudio: 430</TD></TR>
<TR><TD>Consulta de Kardex</TD></TR></TABLE>
<TABLE><TR>{enc}</TR>{"".join(filas)}</TABLE></BODY></HTML>"""


def pagina_periodos(trund: str) -> str:
    ops = "".join(f'<option value="{v}">{n}</option>' for v, n in PERIODOS)
    return f"""<html><body><form method="POST" action="https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/control.p?{_base_qs()}" name="mi_forma">
<select name="HTMLPeriodo" onchange="inicio()"><option value="0">Selecciona</option>{ops}</select>
<input type="hidden" name="HTMLTrund" value=""><input type="hidden" name="HTMLResill" value="40002">
<script>function inicio() {{ document.mi_forma.HTMLTrund.value="{trund}"; document.mi_forma.submit(); }}</script>
</form></body></html>"""


def pagina_calificaciones(periodo: str) -> str:
    nombre = dict(PERIODOS)[periodo]
    filas = "".join("<TR>" + "".join(f"<TD>{_e(x)}</TD>" for x in f) + "</TR>" for f in CALIFICACIONES[periodo])
    enc = "".join(f"<TD><b>{t}</b></TD>" for t in ["Clave", "Materia", "Tip. Inscr", "Gpo.", "Fecha", "Cfs", "Op"])
    return f"""<HTML><BODY><TABLE><TR><TD>Periodo : {nombre.replace('Semestral ', '')}</TD><TD><!-- --></TD></TR>
<TR><TD>Carrera : LIC. EN LENG. Y PROD. AUDIOVISUAL</TD><TD>Plan de Estudio: 430</TD></TR>
<TR><TD>Consulta de Calificacion</TD></TR></TABLE><TABLE><TR>{enc}</TR>{filas}</TABLE></BODY></HTML>"""


def _hora12(h: int, m: int) -> str:
    suf = "am" if h < 12 else "pm"
    h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
    return f"{h12}:{m:02d} {suf}"


def pagina_horario() -> str:
    ini = min(b[1] for b in BLOQUES)
    fin = max(b[1] + b[2] for b in BLOQUES)
    filas = []
    for h in range(ini, fin):
        celdas = []
        for d in range(6):
            b = next((x for x in BLOQUES if x[0] == d and x[1] <= h < x[1] + x[2]), None)
            celdas.append(f'<TD class="text-center p-1"><b>F-01</b> / CO<br>{b[3]}<br>{b[4]}<B> / </B>{b[5]}</TD>' if b
                          else '<TD class="text-center p-1">&nbsp;</TD>')
        filas.append(f'<TR><TD class="text-center"> {_hora12(h, 1)} a<BR> {_hora12(h + 1, 0)}</TD>{"".join(celdas)}</tr>')
    dias = "".join(f"<TH>{d}</TH>" for d in ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"])
    enc_m = "".join(f"<TD><b>{t}</b></TD>" for t in ["Tipo", "Clave Materia", "Materia", "Abreviación de Materia",
                                                      "Unidad Oferta", "Grupo", "Tipo Oferta", "Frec.Pres", "Frec.Línea",
                                                      "Frec.Total", "Cred", "Op", "Depcia."])
    mats = "".join(f"<TR><TD>{t}<TD>{c}<TD>{_e(n)}<TD>{a}<TD>01<TD>{g}<TD>{o}<TD>{fp}<TD>{fl}<TD>{ft}<TD>{cr}<TD>{op}<TD>ARTES VISUALES</TR>"
                   for t, c, n, a, g, o, fp, fl, ft, cr, op in MATERIAS_HORARIO)
    return f"""<html><body class="bg-init"><TABLE><TR><TH></TH>{dias}</TR>{"".join(filas)}</TABLE>
<TABLE><TR>{enc_m}</TR>{mats}</TABLE>
<TABLE><TR><TD>Presenciales</TD><TD>Asíncronas</TD><TD>Totales</TD></TR><TR><TD>9</TD><TD>3</TD><TD>12</TD></TR></TABLE>
</body></html>"""


# ---------------------------------------------------------------------- consultas escolares


def pagina_situacion() -> str:
    return f"""<html><body><table><tr><td>DEPARTAMENTO ESCOLAR Y DE ARCHIVO DE LA UANL</td></tr>
<tr><td>SEMESTRE : Agosto-Diciembre 2026</td></tr><tr><td>ESTUDIANTE: {MATRICULA} LOPEZ GARZA ANA</td></tr></table>
<div>Identificación Virtual Temporal</div><div>LOPEZ</div><div>GARZA</div><div>ANA</div>
<div>División:-Inscripciones y Credencialización</div>
<p>SITUACIÓN DEL ESTUDIANTE: DEFINITIVO</p><p>TIPO DE INSCRIPCIÓN: REINGRESO</p><p>FOTO ACEPTADA: SI</p>
<p>Nota: El tramite es unicamente al estudiante</p><script>alert('Petición realizada');</script></body></html>"""


def pagina_fecha_inscripcion() -> str:
    return """<html><body><h3>Consulta de Horario de Inscripción</h3><p>Agosto-Diciembre 2026</p>
<p>Dia de Inscripcion : 21 Jul 2026</p><p>Hora de Inscripcion : 09:00</p></body></html>"""


def pagina_adeudos(conceptos: list[tuple[str, str, str, str]]) -> str:
    total = sum(float(c[3].replace("$", "").replace(",", "")) for c in conceptos)
    filas = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in conceptos)
    return f"""<html><body><table><tr><td>Fecha :</td><td>08/Octubre/2026</td></tr>
<tr><td>Matrícula :</td><td>{MATRICULA}</td></tr></table>
<table><tr><td>Cuenta</td><td>Cantidad</td><td>Concepto</td><td>Total</td></tr>{filas}
<tr><td>Adeudo</td><td>Total :</td><td>$</td><td>{total:g}</td></tr></table></body></html>"""


def pagina_beca() -> str:
    return f"""<html><body><p>Alumno : {MATRICULA} LOPEZ GARZA ANA</p><a href="#">Cerrar</a>
<p>No cuenta con una solicitud de beca</p></body></html>"""


def pagina_encuestas(encuestas: list[str]) -> str:
    ops = "".join(f'<option value="{i + 1}">{_e(e)}</option>' for i, e in enumerate(encuestas))
    return f"""<html><body><form action="control.p"><p>Seleccionar la Encuesta:</p>
<select name="HTMLEncuesta"><option value="0">Seleccione</option>{ops}</select></form></body></html>"""


def pagina_tramites(tramites: list[tuple[str, str, str, str, str]]) -> str:
    filas = "".join("<tr>" + "".join(f"<td>{_e(x)}</td>" for x in t) + "<td></td></tr>" for t in tramites)
    return f"""<html><body><script>function agregar() {{ alert('Debe Seleccionar el Tipo de Documento'); }}</script>
<p>Agregar Trámite</p><select id="HTMLTramite" name="HTMLTramite"><option value="0">Seleccione</option>
<option value="39">CERTIFICADO ELECTRÓNICO PARCIAL</option><option value="02">CERTIFICADO PARCIAL</option></select>
<table><tr><td>No. Solicitud</td><td>Documento</td><td>Fecha de Solictud</td><td>Importe</td><td>Estatus</td>
<td>Programación de Requisitos ante el DEyA</td></tr>{filas}</table></body></html>"""


def pagina_documentos(estado: str, pendientes: list[str]) -> str:
    extra = "".join(f"<li>{_e(p)}</li>" for p in pendientes)
    return f"<html><body><h2>Entrega de documentos</h2><p>{_e(estado)}</p><ul>{extra}</ul></body></html>"


def pagina_recibo() -> str:
    conceptos = [("0201", "BONO DEPORTIVO", "$60.00"), ("0211", "INSCRIPCION REING LIC.", "$540.00"),
                 ("0222", "SERVICIOS PARA LA ENSEÑANZA", "$1,100.00"), ("0252", "CUOTA ESCOLAR", "$580.00")]
    filas = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in conceptos)
    return f"""<html><body><h3>Recibo de Servicios Académicos y Escolares</h3>
<table><tr><td>PERIODO DE INSCRIPCIÓN:</td></tr><tr><td>Agosto-Diciembre 2026</td></tr>
<tr><td>INSCRIPCIÓN</td></tr><tr><td>REINGRESO - REINGRESO OFICIAL NACIONAL</td></tr></table>
<table><tr><td>CUENTA</td><td>CONCEPTO</td><td>IMPORTE</td></tr>
<tr><td></td><td>CONCEPTOS DEL PERIODO</td><td>$2,280.00</td></tr>{filas}
<tr><td>** Recibo Pagado ** TOTAL</td><td>$ 2,280.00</td></tr></table>
<p>Realiza tu pago preferentemente antes del 29 de Mayo de 2026</p><p>Trámite de becas 26 de Mayo de 2026</p>
<div>Transacción exitosa</div><div>Monto pagado: $ 2,280.00</div><div>Fecha: 02/07/2026</div>
<div>Transacción: Aprobado</div></body></html>"""


def pagina_recibos_internos() -> str:
    return """<html><body><h3>Recibo Interno de Servicios Academicos y Escolares</h3><p>Seleccione la Boleta</p>
<table><tr><td>Boletas pagadas</td></tr><tr><td><a href="javascript:ejecuta('0x0000000000abc999');">RECIBO INTERNO
DE SERVICIOS ACADÉMICOS Y ESCOLARES REINGRESO SUPERIOR AGOSTO-DICIEMBRE 2026&nbsp;-&nbsp;(Agosto-Diciembre 2026)</a>
</td></tr></table><form action="ecoenma01.htm"><input type="hidden" name="HTMLBoleta" value=""></form></body></html>"""


def pagina_datos() -> str:
    def fila(*pares):
        return "<tr>" + "".join(f"<td>{k}</td><td>{v}</td>" for k, v in pares) + "</tr>"
    return f"""<html><body><table><tr><td>Datos Personales del Alumno</td></tr>
<tr><td>IMSS</td></tr>{fila(("Número de SeguroSocial (NSS)", "00000000000"))}
<tr><td>Datos Generales</td></tr>{fila(("Nombre", "ANA"))}{fila(("Apellido Paterno", "LOPEZ"))}
{fila(("CURP", "XXXX000000XXXXXX00"), ("RFC", ""))}{fila(("Correo Universitario", "ana.demo@uanl.edu.mx"))}
<tr><td>Domicilio Local</td></tr>{fila(("Colonia", "COLONIA DEMO"), ("C.P. :", "64000"))}{fila(("Ciudad", "MONTERREY"))}
<tr><td>Trabajo del Alumno</td></tr>{fila(("Empresa/Institucion", ""), ("Dirección", ""))}
</table><table><tr><td>IMSS</td><td></td></tr><tr><td>Datos Generales</td><td></td></tr></table></body></html>"""


def pagina_parciales() -> str:
    return """<html><body><table><tr><td>Clave</td><td>Materia</td><td>Parcial 1</td><td>Parcial 2</td></tr>
<tr><td>401</td><td>Semiótica de la imagen</td><td>88</td><td></td></tr>
<tr><td>402</td><td>Iluminación y fotometría</td><td>91</td><td></td></tr></table></body></html>"""


# ---------------------------------------------------------------------- servidor


@dataclass
class SiaseFalso:
    afis: list[AfiFalsa] = field(default_factory=lambda: deepcopy(AFIS))
    historial: list[EventoFalso] = field(default_factory=lambda: deepcopy(HISTORIAL))
    oficiales: int = 4
    vencer_una_vez: bool = False
    peticiones: list[httpx.Request] = field(default_factory=list)
    registradas: set[int] = field(default_factory=set)
    adeudos: list[tuple[str, str, str, str]] = field(default_factory=list)
    encuestas: list[str] = field(default_factory=list)
    tramites: list[tuple[str, str, str, str, str]] = field(default_factory=list)
    parciales: bool = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.peticiones.append(request)
        url = urlparse(str(request.url))
        pagina = url.path.rsplit("/", 1)[-1]
        qs = {k: v[-1] for k, v in parse_qs(url.query).items()}
        form = {k: v[-1] for k, v in parse_qs(request.content.decode("latin-1")).items()} if request.content else {}
        if pagina == "login.htm":
            return self._r('<form name="inicio"><input type="hidden" name="HTMLToken" value="t0k="></form>')
        if pagina == "eselcarrera.htm":
            return self._r(pagina_login())
        if qs.get("HTMLtrim") != TRIM or self.vencer_una_vez:
            self.vencer_una_vez = False
            return self._r(pagina_error("Procedimiento restringido, iniciar sesion nuevamente."))
        if pagina == "maintop.htm":
            return self._r(pagina_perfil())
        if pagina == "delSavePrereg.htm":
            mes = int(qs.get("HTMLCveMes", "10"))
            area = int(qs.get("HTMLCveArea", "0"))
            afis = [a for a in self.afis if int(a.inicio[3:5]) == mes or int(a.fin[3:5]) >= mes >= int(a.inicio[3:5])]
            if area:
                afis = [a for a in afis if a.area == _AREAS[area]]
            sel = int(qs.get("HTMLCveEvento", "0")) if request.method == "POST" else 0
            return self._r(pagina_afis(afis, mes, area, sel))
        if pagina == "delSavePreReg20":
            eid = int(qs["HTMLCveEvento"])
            afi = next(a for a in self.afis if a.id == eid)
            ya = next((e for e in self.historial if e.id == eid), None)
            if ya:  # misma petición: libera
                self.historial.remove(ya)
                afi.registrados -= 1
                return self._r(pagina_error("El evento fue liberado."))
            self.historial.append(EventoFalso(eid, afi.evento, afi.area, afi.inicio, False, False, 0, "Agosto-Diciembre 2026"))
            afi.registrados += 1
            return self._r(pagina_error("Pre registro guardado."))
        if pagina == "delConsRegEven.htm":
            return self._r(pagina_historial(self.historial, self.oficiales))
        if pagina == "econkdx01.htm":
            return self._r(pagina_kardex())
        if pagina == "econcfs01.htm":
            return self._r(pagina_periodos("econcfs02"))
        if pagina == "echalm01.htm":
            return self._r(pagina_periodos("echalm02"))
        if pagina == "control.p":
            if form.get("HTMLTrund") == "econcfs02":
                return self._r(pagina_calificaciones(form["HTMLPeriodo"]))
            if form.get("HTMLTrund") == "echalm02":
                return self._r(pagina_horario())
        escolares = {
            "ecSitEst01.htm": pagina_situacion,
            "ecohoinsint01.htm": pagina_fecha_inscripcion,
            "ecavpag04.htm": lambda: pagina_adeudos(self.adeudos),
            "bccosobe01.htm": pagina_beca,
            "eenc01.htm": lambda: pagina_encuestas(self.encuestas),
            "eccontram03.htm": lambda: pagina_tramites(self.tramites),
            "ecCargaDocto01.htm": lambda: pagina_documentos("Expediente Completo", []),
            "ecBolRec-v02.htm": pagina_recibo,
            "ecavpag01.htm": pagina_recibos_internos,
            "edatal01.htm": pagina_datos,
            "econeva01.htm": lambda: pagina_periodos("econeva02"),
        }
        if pagina in escolares:
            return self._r(escolares[pagina]())
        if pagina == "control.p" and form.get("HTMLTrund") == "econeva02":
            return self._r(pagina_parciales() if self.parciales else pagina_error("No cuenta con Evaluaciones o Parciales en este periodo."))
        return httpx.Response(404, text="no existe")

    @staticmethod
    def _r(cuerpo: str) -> httpx.Response:
        return httpx.Response(200, content=cuerpo.encode("latin-1", errors="replace"),
                              headers={"content-type": "text/html; charset=ISO-8859-1"})

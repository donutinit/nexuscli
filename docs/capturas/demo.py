"""Un Nexus de mentira para las capturas del README.

Dos materias inventadas, con tareas en todos los estados, rúbricas, recursos, avisos, foro y
un equipo. Ningún dato es real: los nombres de profesores, compañeros y matrículas son de
ejemplo. Responde por endpoint igual que api.nexus.uanl.mx, así el CLI corre sin cambios.
"""

from __future__ import annotations

import json
from copy import deepcopy

import httpx

PESO_DOC = 846_000

PROFA = {"CuentaId": 501, "Nombre": "OFELIA", "ApellidoPaterno": "REYES", "ApellidoMaterno": "SALAZAR", "RolId": 2}
PROFE = {"CuentaId": 502, "Nombre": "MARCO ANTONIO", "ApellidoPaterno": "VELA", "ApellidoMaterno": "", "RolId": 2}

CURSOS = [
    {"CursoId": 100001, "Nombre": "Semiótica de la imagen | AGO26 | 201", "Profesores": [PROFA],
     "FechaInicio": "2026-08-03T08:00:00", "FechaFin": "2026-12-18T23:59:00",
     "Bienvenida": {"Contenido": "<p><strong>Bienvenidos.</strong> Este semestre vamos a leer imágenes.</p>"},
     "Foro": {"ForoId": 9001}},
    {"CursoId": 100002, "Nombre": "Guion cinematográfico | AGO26 | 202", "Profesores": [PROFE],
     "FechaInicio": "2026-08-03T08:00:00", "FechaFin": "2026-12-18T23:59:00", "Foro": {"ForoId": 9002}},
]


def _t(eid, etapa, pos, nombre, valor, ini, fin, equipo=False, cal=None, entregas=(), retros=(), rubrica=True):
    return {"TipoElementoId": 1, "ElementoId": eid, "EtapaId": etapa, "Posicion": pos, "Nombre": nombre,
            "Valor": valor, "FechaInicio": ini, "FechaFin": fin, "FechaLimite": fin, "EnEquipo": equipo,
            "EquipoId": 7003 if equipo else 0, "UsaRubrica": rubrica,
            "Calificacion": {"Valor": cal, "Rubrica": []} if cal is not None else None,
            "Entregas": list(entregas), "Retroalimentaciones": list(retros)}


def _entrega(eid, nombre, fecha, equipo=False):
    return {"EntregaId": eid, "TipoEntrega": 1, "EnEquipo": equipo, "Estado": True,
            "Documento": {"DocumentoId": eid + 1, "Nombre": nombre, "Peso": 2_450_000, "FechaCreacion": fecha,
                          "URL": f"Contenedores D/Demo/{eid}.pdf"}}


def _retro(rid, texto, fecha):
    return {"RetroalimentacionId": rid, "Descripcion": texto, "FechaModificacion": fecha, "DerechoReplica": False,
            "Replicas": None, "Documentos": None}


PORTAFOLIO = {
    100001: [
        _t(41, 1, 1, "Act 1.1 Mapa de conceptos de Peirce y Saussure.", 5, "2026-08-06T15:00:00", "2026-08-14T23:59:00",
           cal=95, entregas=[_entrega(301, "1.1_mapa_conceptos.pdf", "2026-08-13T21:40:00")],
           retros=[_retro(801, "Muy claro el mapa. Cuida la diferencia entre ícono e índice.", "2026-08-17T12:10:00")]),
        _t(42, 1, 2, "Act 1.2 Análisis de un cartel publicitario.", 6, "2026-08-06T15:00:00", "2026-08-21T23:59:00",
           equipo=True, cal=88, entregas=[_entrega(303, "EQUIPO3_ACT1.2.pdf", "2026-08-21T20:02:00", True)]),
        _t(43, 1, 3, "Act 1.3 Glosario ilustrado de la fase 1.", 5, "2026-08-06T15:00:00", "2026-08-28T23:59:00"),
        _t(44, 2, 1, "Act 2.1 Ensayo breve sobre la connotación.", 6, "2026-09-03T15:00:00", "2026-09-25T23:59:00",
           entregas=[_entrega(305, "2.1_ensayo_connotacion.pdf", "2026-09-24T23:11:00")]),
        _t(45, 2, 2, "Act 2.2 Storyboard comentado de una secuencia.", 8, "2026-09-03T15:00:00", "2026-10-09T23:59:00",
           equipo=True),
        _t(46, 2, 3, "Evidencia 2. Análisis semiótico de un videoclip.", 10, "2026-10-12T15:00:00", "2026-10-30T23:59:00",
           equipo=True),
        {**_t(47, 0, 0, "Producto integrador: ensayo visual con sustento teórico", 30, "2026-10-01T08:00:00",
              "2026-12-04T23:59:00", equipo=True), "TipoElementoId": 2, "ElementoId": 900},
    ],
    100002: [
        _t(61, 11, 1, "Escrito: idea y supraidea.", 5, "2026-08-03T08:00:00", "2026-08-09T23:59:00", cal=100,
           entregas=[_entrega(401, "1.1_supraidea.pdf", "2026-08-08T19:00:00")]),
        _t(62, 11, 2, "Diseño de personaje.", 5, "2026-08-10T08:00:00", "2026-08-23T23:59:00",
           entregas=[_entrega(403, "1.2_personaje.pdf", "2026-08-22T18:30:00")]),
        _t(63, 12, 1, "Escaleta de un cortometraje.", 10, "2026-09-28T08:00:00", "2026-10-13T23:59:00"),
        _t(64, 12, 2, "Pitch elevador.", 5, "2026-10-14T08:00:00", "2026-10-25T23:59:00", equipo=True),
        {**_t(65, 0, 0, "Guion de cortometraje", 30, "2026-10-01T08:00:00", "2026-12-02T11:00:00", equipo=True),
         "TipoElementoId": 2, "ElementoId": 910},
    ],
}

ETAPAS = {100001: [(1, 1), (2, 2)], 100002: [(11, 1), (12, 2)]}

INSTRUCCIONES = [
    {"Titulo": "Instrucción general", "Posicion": 0, "Descripcion":
        "<p>1.&nbsp;Lee el documento <strong>\"GI_Act 2.2 Storyboard comentado\"</strong> en Recursos.</p>"
        "<p>2. Revisa la rúbrica para saber cómo se evalúa.</p>"},
    {"Titulo": "Actividades de aprendizaje", "Posicion": 1, "Descripcion":
        "<p>1. Elige una secuencia de máximo dos minutos de una película mexicana.</p>"
        "<p>2. Dibuja su storyboard, un cuadro por plano.</p>"
        "<p>3. Comenta cada cuadro con las categorías de la fase 2:</p>"
        "<p>• denotación y connotación</p><p>• anclaje y relevo</p><p>• punctum y studium</p>"
        "<p>4. Entrega en PDF con el nombre de tu equipo. Ejemplo: EQUIPO3_ACT2.2.</p>"},
]

RUBRICA = {
    "Criterios": [{"CriterioId": 1, "Descripcion": "Selección de la secuencia", "Posicion": 1},
                  {"CriterioId": 2, "Descripcion": "Storyboard", "Posicion": 2},
                  {"CriterioId": 3, "Descripcion": "Comentario semiótico", "Posicion": 3}],
    "NivelDominios": [{"NivelDominioId": 11, "Nombre": "Excelente", "Posicion": 1},
                      {"NivelDominioId": 12, "Nombre": "Suficiente", "Posicion": 2},
                      {"NivelDominioId": 13, "Nombre": "Insuficiente", "Posicion": 3}],
    "CriterioNivelDominios": [
        {"CriterioNivelDominioId": 100 + c * 10 + n, "CriterioId": c, "NivelDominioId": 10 + n,
         "Puntos": pts, "Descripcion": desc}
        for c, fila in {1: [(30, "Secuencia pertinente y justificada."), (20, "Pertinente sin justificar."), (10, "No se justifica.")],
                        2: [(30, "Un cuadro por plano, legible."), (20, "Faltan planos."), (10, "Ilegible.")],
                        3: [(40, "Usa las tres parejas de categorías."), (25, "Usa dos."), (10, "Usa una o ninguna.")]}.items()
        for n, (pts, desc) in enumerate(fila, 1)
    ],
}


def _recursos(eid: int | None) -> dict:
    base = {"RecursoArchivos": [], "RecursosExternos": [], "RecursosTextos": []}
    if eid is None:
        base["RecursoArchivos"] = [
            {"MostrarEstudiante": True, "Posicion": 1, "Documento": _doc(2001, "Programa_Semiotica_de_la_imagen.pdf")},
            {"MostrarEstudiante": True, "Posicion": 2, "Documento": _doc(2002, "Barthes - Retórica de la imagen.pdf")},
        ]
        return base
    clave = {41: "Act 1.1", 42: "Act 1.2", 43: "Act 1.3", 44: "Act 2.1", 45: "Act 2.2", 46: "Ev 2",
             900: "PIA"}.get(eid, str(eid))
    base["RecursoArchivos"] = [
        {"MostrarEstudiante": True, "Posicion": 1, "Documento": _doc(3000 + eid, f"GI_{clave} guía de la actividad.pdf")},
    ]
    if eid == 45:
        base["RecursoArchivos"].append(
            {"MostrarEstudiante": True, "Posicion": 2, "Documento": _doc(2002, "Barthes - Retórica de la imagen.pdf")})
        base["RecursosExternos"] = [{"ExternoId": 5, "Titulo": "Plantilla de storyboard", "MostrarEstudiante": True,
                                     "Contenido": "https://example.org/storyboard.pdf", "Descripcion": "Formato sugerido"}]
        base["RecursosTextos"] = [{"TextoId": 6, "Titulo": "Lectura complementaria", "MostrarEstudiante": True,
                                   "Contenido": "<p>Barthes, R. (1964). <em>Retórica de la imagen</em>.</p>"}]
    return base


def _doc(doc_id: int, nombre: str) -> dict:
    return {"DocumentoId": doc_id, "Nombre": nombre, "Extension": ".pdf", "Peso": PESO_DOC,
            "URL": f"Contenedores D/Demo/{doc_id}.pdf"}


class DemoNexus:
    """httpx.MockTransport: responde como el WebApi de Nexus con los datos de arriba."""

    def __init__(self) -> None:
        self.portafolio = deepcopy(PORTAFOLIO)
        self.avisos: dict[int, list] = {100001: [], 100002: []}
        self.foro: list[dict] = [
            {"TemaComentarioId": 1, "Comentario": "Bienvenidos a la fase 2.", "Cuenta": PROFA,
             "FechaCreacion": "2026-09-03T09:00:00", "Estado": True, "Respuestas": []},
        ]
        self.entregas_extra: list[dict] = []

    def cambios_de_la_semana(self) -> None:
        """Lo que "pasó" entre dos corridas de `novedades`."""
        self.portafolio[100001][1]["Retroalimentaciones"].append(_retro(
            802, "Buen análisis del cartel. Faltó citar a Barthes en la parte de connotación; revisen APA.",
            "2026-10-07T18:20:00"))
        self.portafolio[100002][1]["Calificacion"] = {"Valor": 90, "Rubrica": []}
        self.avisos[100002].append({"AvisoId": 71, "Titulo": "Sesión de pitches", "EsUrgente": True,
                                    "FechaInicio": "2026-10-07T00:00:00", "FechaFin": "2026-10-25T23:59:00",
                                    "Mensaje": "<p>La próxima semana presentamos los pitches por equipo. "
                                               "<strong>Asistan solo en el horario de su equipo.</strong></p>"})
        self.foro.append({"TemaComentarioId": 2, "Cuenta": PROFA, "FechaCreacion": "2026-10-08T08:15:00",
                          "Comentario": "Recuerden: el storyboard de la 2.2 va en PDF, un cuadro por plano.",
                          "Estado": True, "Respuestas": []})

    # ------------------------------------------------------------------ transporte

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET":
            return httpx.Response(200, content=b"%PDF-1.4 demo" + b"." * (PESO_DOC - 13))
        body = json.loads(request.content) if request.content and request.headers.get("content-type", "").startswith("application/json") else {}
        ep = url.split("/WebApi/", 1)[1].rstrip("/")
        return httpx.Response(200, json=self.responder(ep, body))

    def responder(self, ep: str, b: dict) -> dict:
        cid = b.get("CursoId")
        if ep == "Seguridad/ConsultarPerfil":
            return {"Persona": {"Nombre": "ANA", "ApellidoPaterno": "LÓPEZ", "Cuentas": [{"CuentaId": 100200}]}}
        if ep == "Curso/ConsultarCarpetaCursos":
            return {"Carpetas": [{"Cursos": CURSOS}], "Paginacion": {"RegistrosPagina": 10, "RegistrosTotales": 2}}
        if ep == "Curso/ConsultarDetalleCurso":
            c = next(c for c in CURSOS if c["CursoId"] == cid)
            return {"Curso": {**c, "Modalidad": {"Nombre": "Escolarizada"},
                              "Compromiso": {"Descripcion": "<p>a. Entregar a tiempo.</p>"}}}
        if ep == "Estructura/ConsultarEstructura":
            etapas = []
            for eid, pos in ETAPAS[cid]:
                evs = [{"EvidenciaId": e["ElementoId"], "EntregaExtemporanea": False, "EntregarDocumentos": True,
                        "EntregarRecursoExterno": True}
                       for e in self.portafolio[cid] if e["EtapaId"] == eid]
                etapas.append({"EtapaId": eid, "Posicion": pos, "Evidencias": evs})
            pia = next(e for e in self.portafolio[cid] if e["TipoElementoId"] == 2)
            return {"Estructura": {"Etapas": etapas, "ProductoIntegrador": {
                "ProductoIntegradorId": pia["ElementoId"], "EntregarDocumentos": True, "EntregaExtemporanea": False}}}
        if ep == "Portafolio/ConsultarPortafolio":
            return {"ElementosEvaluables": self.portafolio[cid]}
        if ep in ("Estructura/ConsultarDetalleEvidencia", "Estructura/ConsultarDetalleProductoIntegrador"):
            det = {"Contenidos": INSTRUCCIONES, "Tema": [{"TemaId": 9101, "Nombre": "Foro de dudas: fase 2"}]}
            return {"Evidencia": det, "ProductoIntegrador": det}
        if ep == "Recurso/ConsultarRecursos":
            return {"Recursos": _recursos(b.get("ElementoId"))}
        if ep == "Rubrica/ConsultarRubrica":
            return {"Rubrica": RUBRICA}
        if ep == "ProgramaAnalitico/ConsultarProgramaAnalitico":
            return {"ProgramaAnalitico": {}}
        if ep == "Aviso/ConsultarAvisos":
            return {"Avisos": self.avisos.get(cid, [])}
        if ep == "Foro/ConsultarTemas":
            return {"Temas": [{"TemaId": 9101, "Nombre": "Foro de dudas: fase 2", "FechaInicio": "2026-09-01T00:00:00",
                               "FechaFin": "2026-11-01T23:59:00"}] if b.get("ForoId") == 9001 else []}
        if ep == "Foro/ConsultarComentarios":
            return {"Tema": {"TemaId": 9101, "Nombre": "Foro de dudas: fase 2", "Comentarios": self.foro}}
        if ep == "Mensaje/ConsultarConversaciones":
            return {"Conversaciones": []}
        if ep == "Equipo/ConsultarEquipoEstudiante":
            return {"Equipos": [{"EquipoId": 7003, "Nombre": "Equipo 3", "Estudiantes": [
                {"Nombre": "ANA", "ApellidoPaterno": "LÓPEZ"}, {"Nombre": "BRUNO", "ApellidoPaterno": "GARZA"},
                {"Nombre": "CAMILA", "ApellidoPaterno": "RÍOS"}]}]}
        if ep == "Equipo/ActualizarEquipoArchivo":
            return {"Archivo": {"DocumentoId": 5551, "Nombre": "storyboard"}}
        if ep == "Tarea/VincularEntregaEquipo":
            self.entregas_extra.append(_entrega(555, "EQUIPO3_ACT2.2_storyboard.pdf", "2026-10-08T10:31:00", True))
            return {"Entrega": {"EntregaId": 555}}
        if ep == "Tarea/ConsultarEntregas":
            return {"Entregas": self.entregas_extra if b.get("ElementoId") == 45 else []}
        return {}

"""Operaciones de Nexus sobre el cliente HTTP: cursos, tareas, entregas, equipo, etc.

Los cuerpos de cada petición replican lo que manda el Angular de plataformanexus.uanl.mx
(servicios TareaService, EquipoService, ForoService, MensajesService...). Si Nexus cambia,
aquí es donde hay que ajustar.
"""

from __future__ import annotations

import json
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config, texto
from .client import Client, NexusError, campo, campo_archivo
from .materias import Materias

EVIDENCIA = 1
PIA = 2


class NoEncontrado(NexusError):
    pass


class Ambiguo(NexusError):
    def __init__(self, message: str, opciones: list[str]):
        super().__init__(message)
        self.opciones = opciones


@dataclass
class Curso:
    id: int
    nombre: str
    profesores: list[dict] = field(default_factory=list)
    inicio: str | None = None
    fin: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "profesores": self.profesores, "inicio": self.inicio, "fin": self.fin}

    @property
    def corto(self) -> str:
        return texto.curso_corto(self.nombre)


@dataclass
class Tarea:
    curso_id: int
    curso: str
    tipo: int
    id: int
    clave: str
    nombre: str
    valor: float | None
    inicio: datetime | None
    fin: datetime | None
    limite: datetime | None
    en_equipo: bool
    equipo_id: int
    extemporanea: bool = False
    acepta_archivos: bool = True
    acepta_ligas: bool = False
    calificacion: float | None = None
    entregas: list[dict] = field(default_factory=list)
    retros: list[dict] = field(default_factory=list)
    usa_rubrica: bool = False

    @property
    def cierre(self) -> datetime | None:
        """Hasta cuándo acepta entregas."""
        if self.extemporanea and self.limite:
            return self.limite
        # A veces Nexus trae FechaLimite antes de FechaFin; la más temprana es la segura.
        fechas = [d for d in (self.fin, self.limite) if d]
        return min(fechas) if fechas else None

    @property
    def entregas_activas(self) -> list[dict]:
        return [e for e in self.entregas if e.get("Estado", True)]

    @property
    def estado(self) -> str:
        if self.calificacion is not None:
            return "calificada"
        if self.entregas_activas:
            return "entregada"
        if self.cierre and texto.ahora() > self.cierre:
            return "vencida"
        if self.inicio and texto.ahora() < self.inicio:
            return "próxima"
        return "pendiente"

    def as_dict(self) -> dict:
        return {
            "curso_id": self.curso_id,
            "curso": self.curso,
            "tipo": self.tipo,
            "id": self.id,
            "clave": self.clave,
            "nombre": self.nombre,
            "valor": self.valor,
            "inicio": self.inicio.isoformat() if self.inicio else None,
            "fin": self.fin.isoformat() if self.fin else None,
            "limite": self.limite.isoformat() if self.limite else None,
            "en_equipo": self.en_equipo,
            "equipo_id": self.equipo_id,
            "extemporanea": self.extemporanea,
            "acepta_archivos": self.acepta_archivos,
            "acepta_ligas": self.acepta_ligas,
            "estado": self.estado,
            "calificacion": self.calificacion,
            "entregas": self.entregas,
            "retroalimentaciones": self.retros,
        }


class Nexus:
    def __init__(self, client: Client, fresco: bool = False, materias: Materias | None = None) -> None:
        self.c = client
        self.fresco = fresco
        self.materias = materias if materias is not None else Materias()

    # ------------------------------------------------------------------ caché

    def _cache_path(self, clave: str) -> Path:
        return self.c.state / "cache" / f"{clave}.json"

    def _cached(self, clave: str, ttl: float, endpoint: str, body: dict) -> dict:
        path = self._cache_path(clave)
        if not self.fresco:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if time.time() - data["ts"] < ttl:
                    return data["json"]
            except (FileNotFoundError, ValueError, KeyError):
                pass
        j = self.c.call(endpoint, body)
        j.pop("Sesion", None)
        config.escribir_privado(path, json.dumps({"ts": time.time(), "json": j}, ensure_ascii=False))
        return j

    # ------------------------------------------------------------------ cursos

    def cursos(self) -> list[Curso]:
        out: list[Curso] = []
        pagina = 1
        while True:
            j = self._cached(
                f"cursos-{pagina}", 6 * 3600,
                "Curso/ConsultarCarpetaCursos", {"CarpetaId": 0, "Pagina": pagina, "Paginacion": 10},
            )
            for carpeta in j.get("Carpetas") or []:
                for cu in carpeta.get("Cursos") or []:
                    out.append(Curso(
                        id=cu["CursoId"], nombre=cu.get("Nombre") or cu.get("Alias") or str(cu["CursoId"]),
                        profesores=cu.get("Profesores") or [], inicio=cu.get("FechaInicio"), fin=cu.get("FechaFin"),
                        raw=cu,
                    ))
            pag = j.get("Paginacion") or {}
            total = pag.get("RegistrosTotales") or 0
            if pagina * (pag.get("RegistrosPagina") or 10) >= total:
                break
            pagina += 1
        return out

    def curso(self, consulta: str | int | None) -> Curso:
        cursos = self.cursos()
        if consulta is None or consulta == "":
            if len(cursos) == 1:
                return cursos[0]
            raise Ambiguo("Tienes varios cursos; elige uno con -c", [self.etiqueta(c) for c in cursos])
        q = str(consulta).strip()
        if q.isdigit():
            for c in cursos:
                if c.id == int(q):
                    return c
        por_codigo = self.materias.curso_id(q)
        if por_codigo is not None:
            for c in cursos:
                if c.id == por_codigo:
                    return c
            nombre = self.materias.nombres.get(por_codigo) or por_codigo
            raise NoEncontrado(f"{q} es {nombre}, que ya no está activa en Nexus")
        nq = texto.normalizar(q)
        hits = [c for c in cursos if nq in texto.normalizar(c.nombre)]
        if not hits:
            palabras = nq.split()
            hits = [c for c in cursos if all(p in texto.normalizar(c.nombre) for p in palabras)]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise NoEncontrado(f"Ningún curso coincide con {q!r}")
        raise Ambiguo(f"{q!r} coincide con varios cursos", [self.etiqueta(c) for c in hits])

    def etiqueta(self, c: Curso) -> str:
        cod = self.materias.codigo(c.id)
        return f"{c.id}  {cod or '-':<6} {c.nombre}"

    def corto(self, curso_id: int, nombre: str) -> str:
        """Código de la materia si tiene, si no el nombre corto."""
        return self.materias.codigo(curso_id) or texto.curso_corto(nombre)

    def cursos_filtrados(self, consulta: str | None) -> list[Curso]:
        return [self.curso(consulta)] if consulta else self.cursos()

    def detalle_curso(self, curso_id: int) -> dict:
        return self._cached(f"curso-{curso_id}", 12 * 3600, "Curso/ConsultarDetalleCurso", {"CursoId": curso_id}).get("Curso") or {}

    # ------------------------------------------------------------------ tareas

    def estructura(self, curso_id: int) -> dict:
        return self._cached(f"estructura-{curso_id}", 3 * 3600, "Estructura/ConsultarEstructura", {"CursoId": curso_id}).get("Estructura") or {}

    def portafolio(self, curso_id: int) -> list[dict]:
        return self.c.call("Portafolio/ConsultarPortafolio", {"CursoId": curso_id}).get("ElementosEvaluables") or []

    def tareas(self, curso: Curso) -> list[Tarea]:
        est = self.estructura(curso.id)
        etapa_pos = {et["EtapaId"]: et.get("Posicion") for et in est.get("Etapas") or []}
        meta: dict[tuple[int, int], dict] = {}
        for et in est.get("Etapas") or []:
            for ev in et.get("Evidencias") or []:
                meta[(EVIDENCIA, ev["EvidenciaId"])] = ev
        pi = est.get("ProductoIntegrador")
        if pi:
            meta[(PIA, pi["ProductoIntegradorId"])] = pi

        out: list[Tarea] = []
        for e in self.portafolio(curso.id):
            tipo, eid = e.get("TipoElementoId"), e.get("ElementoId")
            m = meta.get((tipo, eid), {})
            if tipo == EVIDENCIA:
                clave = f"{etapa_pos.get(e.get('EtapaId'), '?')}.{e.get('Posicion', '?')}"
            elif tipo == PIA:
                clave = "PIA"
            else:
                clave = f"T{tipo}"
            cal = (e.get("Calificacion") or {}).get("Valor")
            out.append(Tarea(
                curso_id=curso.id, curso=curso.nombre, tipo=tipo, id=eid, clave=clave,
                nombre=(e.get("Nombre") or m.get("Descripcion") or "").strip(),
                valor=e.get("Valor"),
                inicio=texto.fecha(e.get("FechaInicio")), fin=texto.fecha(e.get("FechaFin")),
                limite=texto.fecha(e.get("FechaLimite") or m.get("FechaLimite")),
                en_equipo=bool(e.get("EnEquipo")), equipo_id=int(e.get("EquipoId") or 0),
                extemporanea=bool(m.get("EntregaExtemporanea")),
                acepta_archivos=bool(m.get("EntregarDocumentos", True)),
                acepta_ligas=bool(m.get("EntregarRecursoExterno", False)),
                calificacion=cal, entregas=e.get("Entregas") or [], retros=e.get("Retroalimentaciones") or [],
                usa_rubrica=bool(e.get("UsaRubrica")),
            ))
        return out

    def todas_las_tareas(self, curso: str | None = None) -> list[Tarea]:
        out: list[Tarea] = []
        for c in self.cursos_filtrados(curso):
            out.extend(self.tareas(c))
        return out

    def tarea(self, consulta: str, curso: str | None = None) -> Tarea:
        tareas = self.todas_las_tareas(curso)
        q = consulta.strip()
        nq = texto.normalizar(q)
        hits: list[Tarea] = []
        if q.isdigit() and len(q) >= 4:
            hits = [t for t in tareas if t.id == int(q)]
        if not hits:
            hits = [t for t in tareas if texto.normalizar(t.clave) == nq]
        if not hits:
            hits = [t for t in tareas if nq in texto.normalizar(t.nombre)]
        if not hits:
            palabras = nq.split()
            hits = [t for t in tareas if all(p in texto.normalizar(t.nombre) for p in palabras)]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise NoEncontrado(f"Ninguna tarea coincide con {q!r}" + (f" en {curso!r}" if curso else ""))
        raise Ambiguo(
            f"{q!r} coincide con varias tareas; usa el id o -c CURSO",
            [f"{t.id}  {t.clave:<5} {texto.curso_corto(t.curso)}: {t.nombre}" for t in hits],
        )

    def detalle_tarea(self, t: Tarea) -> dict:
        if t.tipo == PIA:
            j = self.c.call("Estructura/ConsultarDetalleProductoIntegrador", {"CursoId": t.curso_id, "ProductoIntegradorId": t.id})
            return j.get("ProductoIntegrador") or {}
        j = self.c.call("Estructura/ConsultarDetalleEvidencia", {"EvidenciaId": t.id, "CursoId": t.curso_id})
        return j.get("Evidencia") or {}

    # ------------------------------------------------------------------ entregas

    def entregas(self, t: Tarea) -> list[dict]:
        j = self.c.call("Tarea/ConsultarEntregas", {"CursoId": t.curso_id, "ElementoId": t.id, "TipoElementoId": t.tipo})
        return j.get("Entregas") or []

    def equipo(self, curso_id: int) -> dict | None:
        equipos = self.c.call("Equipo/ConsultarEquipoEstudiante", {"CursoId": curso_id}).get("Equipos") or []
        return equipos[0] if equipos else None

    def archivos_equipo(self, t: Tarea, equipo_id: int, carpeta_id: int = 0) -> dict:
        j = self.c.call("Equipo/ConsultarArchivosCarpetas", {
            "EquipoId": equipo_id, "CarpetaId": carpeta_id, "ElementoId": t.id, "TipoElementoId": t.tipo,
        })
        j.pop("Sesion", None)
        return j

    def subir_archivo(self, t: Tarea, archivo: Path, equipo_id: int | None) -> dict:
        """Entrega un archivo. Con equipo_id: lo sube a la carpeta del equipo y lo vincula
        como entrega del equipo (lo mismo que "Entregar > En Equipo" en la web)."""
        with ExitStack() as stack:
            doc = campo_archivo("Documento", archivo)
            stack.callback(doc[1][1].close)
            if equipo_id:
                campos = [
                    doc,
                    campo("EntregaId", 0),
                    campo("TipoElementoId", t.tipo),
                    campo("ElementoId", t.id),
                    campo("EnEquipo", True),
                    campo("Estado", True),
                    campo("NombreDocumento", archivo.name),
                    campo("CursoId", t.curso_id),
                    campo("EquipoId", equipo_id),
                    campo("CarpetaId", 0),
                ]
                subida = self.c.upload("Equipo/ActualizarEquipoArchivo", campos)
                documento = subida.get("Archivo") or subida.get("Documento") or {}
                doc_id = documento.get("DocumentoId")
                if not doc_id:
                    raise NexusError(f"Nexus no devolvió el documento subido: {_resumen(subida)}")
                vinculo = self.vincular_equipo(t, equipo_id, doc_id, tipo_entrega=1)
                return {"subida": _sin_sesion(subida), "vinculo": _sin_sesion(vinculo)}
            campos = [
                doc,
                campo("EntregaId", 0),
                campo("TipoElementoId", t.tipo),
                campo("ElementoId", t.id),
                campo("EnEquipo", False),
                campo("Estado", True),
                campo("NombreDocumento", archivo.name),
                campo("CursoId", t.curso_id),
            ]
            return {"subida": _sin_sesion(self.c.upload("Tarea/ActualizarEntregaDocumento", campos))}

    def vincular_equipo(self, t: Tarea, equipo_id: int, recurso_id: int, tipo_entrega: int, estado: bool = True) -> dict:
        return self.c.call("Tarea/VincularEntregaEquipo", {
            "EquipoId": equipo_id,
            "EntregaId": 0,
            "CursoId": t.curso_id,
            "ElementoId": t.id,
            "TipoElementoId": t.tipo,
            "TareaRecursoId": recurso_id,
            "Estado": estado,
            "TipoEntrega": tipo_entrega,
        }, peso=1.5)

    def entregar_liga(self, t: Tarea, url: str, titulo: str, equipo_id: int | None, embed: bool = False) -> dict:
        j = self.c.call("Tarea/ActualizarEntregaRecursoExterno", {
            "CursoId": t.curso_id,
            "Entrega": {"EntregaId": 0, "TipoElementoId": t.tipo, "ElementoId": t.id, "Estado": True},
            "RecursoExterno": {
                "ExternoId": 0, "Entregado": False, "Estado": True,
                "TipoRecursoExternoId": 1 if embed else 2, "Titulo": titulo, "Contenido": url,
            },
            "EnEquipo": bool(equipo_id),
            "EquipoId": equipo_id or 0,
        }, peso=2.0)
        out = {"entrega": _sin_sesion(j)}
        if equipo_id:
            externo = ((j.get("Entrega") or {}).get("RecursoExterno") or {}).get("ExternoId")
            if not externo:
                raise NexusError(f"Nexus no devolvió el recurso externo: {_resumen(j)}")
            out["vinculo"] = _sin_sesion(self.vincular_equipo(t, equipo_id, externo, tipo_entrega=2))
        return out

    def borrar_entrega(self, t: Tarea, entrega: dict) -> dict:
        if entrega.get("TipoEntrega") == 2:
            recurso = dict(entrega.get("RecursoExterno") or {})
            recurso["Estado"] = False
            return _sin_sesion(self.c.call("Tarea/ActualizarEntregaRecursoExterno", {
                "CursoId": t.curso_id,
                "Entrega": {"EntregaId": entrega["EntregaId"], "TipoElementoId": t.tipo, "ElementoId": t.id, "Estado": False},
                "RecursoExterno": recurso,
                "EnEquipo": bool(entrega.get("EnEquipo")),
                "EquipoId": 0,
            }, peso=2.0))
        # TareaEliminarDocumentoComponent: mismo endpoint de subida, sin archivo y Estado 0.
        campos = [
            campo("Documento", None),
            campo("NombreDocumento", None),
            campo("DocumentoId", None),
            campo("CursoId", t.curso_id),
            campo("EntregaId", entrega["EntregaId"]),
            campo("TipoElementoId", t.tipo),
            campo("ElementoId", t.id),
            campo("EnEquipo", bool(entrega.get("EnEquipo"))),
            campo("Estado", "0"),
        ]
        return _sin_sesion(self.c.upload("Tarea/ActualizarEntregaDocumento", campos))

    def borrar_archivo_equipo(self, equipo_id: int, documento_id: int) -> dict:
        return _sin_sesion(self.c.call("Equipo/EliminarEquipoArchivo", {
            "EquipoArchivo": {"DocumentoId": documento_id, "EquipoId": equipo_id},
        }, peso=2.0))

    # ------------------------------------------------------------------ comentarios

    def responder_retro(self, curso_id: int, retro_id: int, comentario: str) -> dict:
        return _sin_sesion(self.c.call("Retroalimentacion/ActualizarComentarioRetroalimentacion", {
            "CursoId": curso_id, "RetroalimentacionId": retro_id, "ReplicaId": 0,
            "Comentario": comentario, "Estado": True,
        }, peso=2.0))

    # ------------------------------------------------------------------ avisos, recursos

    def avisos(self, curso_id: int) -> list[dict]:
        return self.c.call("Aviso/ConsultarAvisos", {"CursoId": curso_id, "Asignados": True}).get("Avisos") or []

    def recursos(self, curso_id: int) -> dict:
        return self.c.call("Recurso/ConsultarRecursos", {"CursoId": curso_id}).get("Recursos") or {}

    def recursos_tarea(self, t: Tarea) -> dict:
        """Los de la pestaña Recursos de la tarea (RecursosService.ConsultarRecursos con Elemento)."""
        return self.c.call("Recurso/ConsultarRecursos", {
            "CursoId": t.curso_id, "ElementoId": t.id, "TipoElementoId": t.tipo,
        }).get("Recursos") or {}

    def rubrica(self, t: Tarea) -> dict:
        return self.c.call("Rubrica/ConsultarRubrica", {"TipoElementoId": t.tipo, "ElementoId": t.id}).get("Rubrica") or {}

    def programa(self, curso_id: int) -> dict:
        return self.c.call("ProgramaAnalitico/ConsultarProgramaAnalitico", {"CursoId": curso_id}).get("ProgramaAnalitico") or {}

    def calificacion_rubrica(self, curso_id: int) -> dict[tuple[int, int], set[int]]:
        """(tipo, id) -> CriterioNivelDominioId que marcó el profesor."""
        out: dict[tuple[int, int], set[int]] = {}
        for e in self.portafolio(curso_id):
            sel = {r.get("CriterioNivelDominioId") for r in (e.get("Calificacion") or {}).get("Rubrica") or []}
            out[(e.get("TipoElementoId"), e.get("ElementoId"))] = {x for x in sel if x}
        return out

    # ------------------------------------------------------------------ foro

    def foro_id(self, curso_id: int) -> int | None:
        foro = self.detalle_curso(curso_id).get("Foro") or {}
        return foro.get("ForoId")

    def foro_temas(self, curso_id: int) -> list[dict]:
        fid = self.foro_id(curso_id)
        if not fid:
            return []
        return self.c.call("Foro/ConsultarTemas/", {"ForoId": fid}).get("Temas") or []

    def foro_tema(self, curso_id: int, tema_id: int) -> dict:
        j = self.c.call("Foro/ConsultarComentarios/", {"CursoId": curso_id, "TemaId": tema_id})
        return j.get("Tema") or {}

    def foro_comentar(self, tema_id: int, comentario: str, padre_id: int = 0) -> dict:
        return _sin_sesion(self.c.call("Foro/ActualizarTemaComentario/", {
            "TemaComentario": {
                "ComentariosHijos": [], "Respuestas": [],
                "TemaComentarioId": 0, "TemaId": tema_id, "ComentarioPadreId": padre_id,
                "Comentario": comentario, "EstadoComentarioId": 1, "EsRetroalimentacion": False, "Estado": True,
            },
        }, peso=2.0))

    # ------------------------------------------------------------------ mensajes

    def conversaciones(self, curso_id: int) -> list[dict]:
        return self.c.call("Mensaje/ConsultarConversaciones/", {"CursoId": curso_id}).get("Conversaciones") or []

    def mensajes(self, conversacion_id: int) -> dict:
        j = self.c.call("Mensaje/ConsultarConversacionMensaje", {"ConversacionId": conversacion_id})
        j.pop("Sesion", None)
        return j

    def enviar_mensaje(self, conversacion_id: int, mensaje: str) -> dict:
        s = self.c.sesion()
        return _sin_sesion(self.c.call("Mensaje/ActualizarMensajeConversacion", {
            "MensajeConversacion": {
                "Mensaje": mensaje, "MensajeConversacionId": 0, "ConversacionId": conversacion_id,
                "EmisorCuentaId": s.cuenta_id, "Estado": True,
            },
        }, peso=2.0))

    def nueva_conversacion(self, curso_id: int, nombre: str, integrantes: list[dict]) -> dict:
        return _sin_sesion(self.c.call("Mensaje/ActualizarConversacion", {
            "Conversacion": {
                "IntegranteConversacion": [
                    {"IntegranteConversacionId": 0, "CuentaId": i["CuentaId"], "RolId": i.get("RolId", 2), "Estado": True}
                    for i in integrantes
                ],
                "ConversacionId": 0, "EnviarCorreo": False, "Estado": True,
                "CursoId": curso_id, "EsGrupo": False, "Nombre": nombre,
            },
        }, peso=2.0))


def _sin_sesion(j: Any) -> Any:
    if isinstance(j, dict):
        return {k: v for k, v in j.items() if k != "Sesion"}
    return j


def _resumen(j: Any) -> str:
    return texto.recortar(json.dumps(_sin_sesion(j), ensure_ascii=False), 300)


def documentos_en(obj: Any) -> list[dict]:
    """Todos los objetos con forma de Documento (DocumentoId + URL) dentro de una respuesta."""
    out: list[dict] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if x.get("DocumentoId") and x.get("URL"):
                out.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return out

"""nexuscli: Nexus UANL desde la terminal."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from . import __version__, config, texto
from .estilo import ancho, pintar
from .client import Client, LoginError, NexusError
from .nexus import EVIDENCIA, Ambiguo, Nexus, NoEncontrado, Tarea, documentos_en
from .pace import PERFILES, Pacer
from .materias import CodigoError, avisos_de_cierre, proponer, registrar_clon, ultimo_clon
from .siase import SiaseError
from .store import Visto, huella

# ---------------------------------------------------------------------- salida


class Salida:
    def __init__(self, como_json: bool) -> None:
        self.json = como_json

    def emitir(self, data: Any, texto_fn: Callable[[], None]) -> None:
        if self.json:
            print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        else:
            texto_fn()


def tabla(filas: list[list[Any]], encabezados: list[str]) -> None:
    """Columnas alineadas; las celdas pueden traer color (se mide el ancho visible)."""
    if not filas:
        return
    celdas = [[str(c) for c in f] for f in filas]
    anchos = [max(len(encabezados[i]), *(ancho(f[i]) for f in celdas)) for i in range(len(encabezados))]

    def linea(cols: list[str]) -> str:
        return "  ".join(c + " " * (anchos[i] - ancho(c)) for i, c in enumerate(cols)).rstrip()

    print(pintar(linea(encabezados), "tenue"))
    for f in celdas:
        print(linea(f))


def confirmar(pregunta: str, si: bool) -> None:
    if si:
        return
    if not sys.stdin.isatty():
        raise SystemExit("No hay terminal para confirmar. Revisa el resumen de arriba y repite con -y.")
    resp = input(f"{pregunta} [s/N] ").strip().lower()
    if resp not in ("s", "si", "sí", "y", "yes"):
        raise SystemExit("Cancelado.")


def indent(s: str, n: int = 4) -> str:
    pad = " " * n
    return "\n".join(pad + ln if ln else "" for ln in s.splitlines())


ESTADO_MARCA = {
    "calificada": "✓",
    "entregada": "✓",
    "pendiente": "·",
    "próxima": "…",
    "vencida": "✗",
}


ESTADO_COLOR = {"calificada": "oliva", "entregada": "oliva", "pendiente": "naranja", "próxima": "tenue",
                "vencida": "rojo"}


def fmt_estado(t: Tarea) -> str:
    if t.estado == "calificada":
        return pintar(f"{'✓' if t.calificacion else '✗'} {round(t.calificacion, 1):g}", "oliva" if t.calificacion else "rojo")
    return pintar(f"{ESTADO_MARCA.get(t.estado, '')} {t.estado}", ESTADO_COLOR.get(t.estado))


def fmt_vence(t: Tarea) -> str:
    d = t.cierre
    if d is None:
        return "-"
    if t.estado not in ("pendiente", "próxima"):
        return pintar(texto.fmt_fecha(d), "tenue")
    urgente = (d - texto.ahora()).total_seconds() < 3 * 86400
    return texto.fmt_fecha(d) + " " + pintar(f"({texto.relativo(d)})", "naranja" if urgente else "tenue")


def nombre_entrega(e: dict) -> str:
    doc = e.get("Documento") or {}
    ext = e.get("RecursoExterno") or {}
    if e.get("TipoEntrega") == 2 or (ext.get("ExternoId") and not doc):
        return f"{ext.get('Titulo') or 'liga'} <{ext.get('Contenido') or ''}>"
    return doc.get("Nombre") or "?"


def fecha_entrega(e: dict) -> str:
    doc = e.get("Documento") or {}
    ext = e.get("RecursoExterno") or {}
    return texto.fmt_fecha(texto.fecha(doc.get("FechaCreacion") or ext.get("FechaModificacion") or e.get("FechaModificacion")))


def autor(p: dict | None) -> str:
    if not p:
        return "?"
    return " ".join(x for x in (p.get("Nombre"), p.get("ApellidoPaterno"), p.get("ApellidoMaterno")) if x).title() or "?"


# ---------------------------------------------------------------------- comandos


def cmd_login(nx: Nexus, args, out: Salida) -> None:
    nx.c.olvidar_sesion()
    s = nx.c.login()
    data = {"nombre": s.nombre, "matricula": s.matricula, "cuenta_id": s.cuenta_id, "expira": s.expira}
    out.emitir(data, lambda: print(
        f"Sesión iniciada: {s.nombre.title()} ({s.matricula}). Vigente hasta {texto.fmt_fecha(_ts(s.expira))}."
    ))


def cmd_logout(nx: Nexus, args, out: Salida) -> None:
    s = nx.c.cargar_sesion()
    if s and s.vigente:
        nx.c._sesion = s
        try:
            nx.c._post("Seguridad/FinalizarSesion", {})
        except NexusError:
            pass
    nx.c.olvidar_sesion()
    out.emitir({"ok": True}, lambda: print("Sesión cerrada y borrada de este equipo."))


def cmd_doctor(nx: Nexus, args, out: Salida) -> None:
    checks: list[tuple[str, bool, str]] = []
    try:
        cred = config.load_credentials()
        checks.append(("credenciales", True, cred.origen))
    except config.CredencialesError as e:
        checks.append(("credenciales", False, str(e).splitlines()[0]))
    s = nx.c.cargar_sesion()
    if s and s.vigente:
        checks.append(("sesión guardada", True, f"{s.nombre.title()}, vence {texto.fmt_fecha(_ts(s.expira))}"))
    else:
        checks.append(("sesión guardada", True, "no hay o expiró; se hará login al usarla"))
    try:
        cursos = nx.cursos()
        checks.append(("API de Nexus", True, f"{len(cursos)} cursos"))
    except (NexusError, config.CredencialesError) as e:
        checks.append(("API de Nexus", False, str(e)))
    checks.append(("pausas", True, f"perfil {nx.c.pacer.nombre}"))
    checks.append(("estado local", True, str(nx.c.state)))
    ok = all(c[1] for c in checks)
    out.emitir({"ok": ok, "checks": [{"check": n, "ok": o, "detalle": d} for n, o, d in checks]}, lambda: [
        print(f"{'✓' if o else '✗'} {n}: {d}") for n, o, d in checks
    ])
    if not ok:
        raise SystemExit(1)


def proponer_codigo(nx: Nexus, nombre: str, usados: set[str]) -> str:
    """La abreviatura oficial de SIASE si ya se conoce (CRNG, ANAU...); si no, una inventada."""
    from .siase import abreviatura_oficial
    oficial = abreviatura_oficial(nx.c.state, nombre)
    if oficial and oficial not in usados:
        return oficial
    return proponer(nombre, usados)


def _fila_materia(nx: Nexus, c, usados: set[str]) -> dict:
    cod = nx.materias.codigo(c.id)
    propuesta = None if cod else proponer_codigo(nx, c.nombre, usados)
    if propuesta:
        usados.add(propuesta)
    clon = ultimo_clon(nx.c.state, c.id)
    return {**c.as_dict(), "codigo": cod, "codigo_propuesto": propuesta, "clon": clon}


def _materias(nx: Nexus) -> list[dict]:
    cursos = nx.cursos()
    usados = set(nx.materias.codigos.values())
    return [_fila_materia(nx, c, usados) for c in cursos]


def avisar_cierres(nx: Nexus, cursos, out: Salida) -> list[dict]:
    """Avisos de materias por terminar sin clon reciente. En texto van a stderr."""
    avisos = avisos_de_cierre(cursos, nx.materias, nx.c.state)
    if avisos and not out.json:
        for a in avisos:
            print(f"⚠ {a.texto}.\n  {a.comando}", file=sys.stderr)
    return [{"curso_id": a.curso_id, "curso": a.curso, "motivo": a.motivo, "texto": a.texto, "comando": a.comando}
            for a in avisos]


def cmd_cursos(nx: Nexus, args, out: Salida) -> None:
    filas = _materias(nx)

    def txt():
        tabla([
            [f["id"], f["codigo"] or f"{f['codigo_propuesto']}?", f["nombre"],
             ", ".join(autor(p) for p in f["profesores"]), texto.fmt_fecha(texto.fecha(f["fin"]), False),
             texto.fmt_fecha(texto.fecha(f["clon"]["sincronizado"]), False) if f["clon"] else "-"]
            for f in filas
        ], ["ID", "CÓDIGO", "CURSO", "PROFESOR", "TERMINA", "CLON"])
        sin = [f for f in filas if not f["codigo"]]
        if sin:
            print("\nCon '?' es una propuesta. Confírmala con `nexuscli codigo "
                  f"{sin[0]['id']} {sin[0]['codigo_propuesto']}`, o todas con `nexuscli codigo --aceptar`.")
            from .siase import abreviaturas_path
            if not abreviaturas_path(nx.c.state).exists():
                print(pintar("Corre `nexuscli siase horario` una vez y las propuestas usarán las abreviaturas "
                             "oficiales de SIASE.", "tenue"))

    out.emitir(filas, txt)
    avisar_cierres(nx, nx.cursos(), out)


def cmd_codigo(nx: Nexus, args, out: Salida) -> None:
    m = nx.materias
    if args.aceptar:
        hechos = []
        for f in _materias(nx):
            if not f["codigo"]:
                m.asignar(f["id"], f["codigo_propuesto"], f["nombre"])
                hechos.append(f)
        out.emitir(hechos, lambda: print("\n".join(f"{f['id']} → {f['codigo_propuesto']}  ({f['nombre']})" for f in hechos)
                                         or "Todas tus materias ya tienen código."))
        return
    if not args.curso:
        activas = {f["id"]: f for f in _materias(nx)}
        filas = [[f["id"], f["codigo"] or f"{f['codigo_propuesto']}?", f["nombre"]] for f in activas.values()]
        filas += [[cid, cod, f"{m.nombres.get(cid) or ''} (ya no está activa)"]
                  for cid, cod in m.codigos.items() if cid not in activas]
        out.emitir({"archivo": str(m.path), "materias": filas}, lambda: (
            tabla(filas, ["ID", "CÓDIGO", "CURSO"]), print(f"\nArchivo: {m.path}")))
        return
    c = nx.curso(args.curso)
    if args.quitar:
        ok = m.quitar(c.id)
        out.emitir({"quitado": ok}, lambda: print(f"Quitado el código de {c.nombre}." if ok else "No tenía código."))
        return
    if not args.codigo:
        cod = m.codigo(c.id)
        prop = proponer_codigo(nx, c.nombre, set(m.codigos.values()))
        out.emitir({"id": c.id, "codigo": cod, "codigo_propuesto": None if cod else prop}, lambda: print(
            f"{c.id} {cod}  ({c.nombre})" if cod else f"{c.nombre} no tiene código. Propuesta: {prop}"))
        return
    try:
        cod = m.asignar(c.id, args.codigo, c.nombre)
    except CodigoError as e:
        raise SystemExit(str(e))
    out.emitir({"id": c.id, "codigo": cod}, lambda: print(f"{c.id} → {cod}  ({c.nombre})"))


def cmd_tareas(nx: Nexus, args, out: Salida) -> None:
    tareas = nx.todas_las_tareas(args.curso)
    if args.pendientes:
        tareas = [t for t in tareas if t.estado in ("pendiente", "próxima")]
    if args.semana:
        ahora = texto.ahora()
        tareas = [t for t in tareas if t.cierre and 0 <= (t.cierre - ahora).total_seconds() <= 7 * 86400]
    tareas.sort(key=lambda t: (t.cierre or texto.ahora().replace(year=9999)))
    varios = len({t.curso_id for t in tareas}) > 1

    def txt():
        if not tareas:
            print("Nada por aquí.")
            return
        filas = []
        for t in tareas:
            fila = [pintar(t.clave, negrita=True), pintar(str(t.id), "tenue"), fmt_estado(t), fmt_vence(t),
                    f"{t.valor:g}" if t.valor is not None else "-",
                    "equipo" if t.en_equipo else "indiv", texto.recortar(t.nombre, 48)]
            if varios:
                fila.append(pintar(texto.recortar(nx.corto(t.curso_id, t.curso), 24), "hueso"))
            filas.append(fila)
        tabla(filas, ["#", "ID", "ESTADO", "CIERRA", "PTS", "MODO", "TAREA"] + (["CURSO"] if varios else []))

    out.emitir([t.as_dict() for t in tareas], txt)
    avisar_cierres(nx, nx.cursos_filtrados(args.curso), out)


def cmd_tarea(nx: Nexus, args, out: Salida) -> None:
    t = nx.tarea(args.tarea, args.curso)
    det = nx.detalle_tarea(t)
    contenidos = sorted(det.get("Contenidos") or [], key=lambda c: c.get("Posicion") or 0)
    docs = documentos_en(det.get("Contenidos"))

    def txt():
        print(pintar(f"{t.clave}  {t.nombre}", negrita=True))
        print(pintar(f"{texto.curso_corto(t.curso)} · id {t.id} · {t.valor:g} pts · {'en equipo' if t.en_equipo else 'individual'}", "tenue"))
        print(f"Abre {texto.fmt_fecha(t.inicio)} · cierra {texto.fmt_fecha(t.fin)}"
              + (f" · extemporánea hasta {texto.fmt_fecha(t.limite)}" if t.extemporanea and t.limite else ""))
        acepta = [x for x, ok in (("archivos", t.acepta_archivos), ("ligas", t.acepta_ligas)) if ok]
        print(f"Estado: {fmt_estado(t)} · acepta {', '.join(acepta) or 'nada'}"
              + (" · con rúbrica" if t.usa_rubrica else ""))
        for c in contenidos:
            cuerpo = texto.html_a_texto(c.get("Descripcion"))
            if cuerpo:
                print(f"\n{pintar(c.get('Titulo') or 'Contenido', 'naranja', negrita=True)}\n{cuerpo}")
        if docs:
            print("\n" + pintar("Archivos", "naranja", negrita=True))
            for d in docs:
                print(f"  {d['DocumentoId']}  {d.get('Nombre')} ({texto.tamano(d.get('Peso'))})")
        print("\n" + pintar("Entregas", "naranja", negrita=True))
        _imprimir_entregas(t.entregas)
        if t.retros:
            print("\n" + pintar("Comentarios del profesor", "naranja", negrita=True))
            for r in t.retros:
                _imprimir_retro(r)

    out.emitir({**t.as_dict(), "detalle": det}, txt)


def _imprimir_entregas(entregas: list[dict]) -> None:
    activas = [e for e in entregas if e.get("Estado", True)]
    if not activas:
        print("  (ninguna)")
        return
    for e in activas:
        doc = e.get("Documento") or {}
        extra = f" ({texto.tamano(doc.get('Peso'))})" if doc.get("Peso") else ""
        modo = "equipo" if e.get("EnEquipo") else "indiv"
        print(f"  {e.get('EntregaId')}  {nombre_entrega(e)}{extra} · {modo} · {fecha_entrega(e)}"
              + (f" · doc {doc['DocumentoId']}" if doc.get("DocumentoId") else ""))


def _imprimir_retro(r: dict, tarea: str | None = None) -> None:
    fecha = texto.fmt_fecha(texto.fecha(r.get("FechaModificacion")))
    cab = f"  [{r.get('RetroalimentacionId')}] {fecha}"
    if tarea:
        cab += f" · {tarea}"
    if r.get("DerechoReplica"):
        cab += " · admite respuesta"
    print(pintar(cab, "vino"))
    print(indent(texto.html_a_texto(r.get("Descripcion")) or "(sin texto)", 4))
    for d in documentos_en(r.get("Documentos")):
        print(f"    adjunto: {d['DocumentoId']}  {d.get('Nombre')}")
    for rep in r.get("Replicas") or []:
        quien = autor(rep.get("Cuenta") or rep.get("Persona"))
        print(indent(f"↳ {quien}: {texto.html_a_texto(rep.get('Comentario'))}", 6))


def cmd_entregas(nx: Nexus, args, out: Salida) -> None:
    t = nx.tarea(args.tarea, args.curso)
    entregas = nx.entregas(t)

    def txt():
        print(f"{t.clave} {t.nombre} ({texto.curso_corto(t.curso)})")
        _imprimir_entregas(entregas)

    out.emitir({"tarea": t.as_dict(), "entregas": entregas}, txt)


def _modo_equipo(nx: Nexus, t: Tarea, args) -> tuple[int | None, dict | None]:
    if args.individual and args.equipo:
        raise SystemExit("Usa --individual o --equipo, no los dos.")
    quiere_equipo = args.equipo or (t.en_equipo and not args.individual)
    if not quiere_equipo:
        return None, None
    if not t.en_equipo:
        raise SystemExit(f"{t.clave} {t.nombre} es individual; quita --equipo.")
    eq = nx.equipo(t.curso_id)
    if not eq:
        raise SystemExit("No tienes equipo en este curso. Usa --individual o pídele al profesor que te asigne.")
    return int(eq["EquipoId"]), eq


def _resumen_tarea(t: Tarea, equipo: dict | None) -> list[str]:
    lineas = [f"Tarea:  {t.clave} {t.nombre}", f"Curso:  {t.curso}"]
    if equipo:
        miembros = ", ".join(autor(e).split(" ")[0] for e in equipo.get("Estudiantes") or [])
        lineas.append(f"Modo:   en equipo ({equipo.get('Nombre')}: {miembros})")
    else:
        lineas.append("Modo:   individual")
    if t.cierre:
        cerrada = texto.ahora() > t.cierre
        lineas.append(f"Cierra: {texto.fmt_fecha(t.cierre)}" + ("  ⚠ YA CERRÓ" if cerrada else f" ({texto.relativo(t.cierre)})"))
    if t.entregas_activas:
        lineas.append(f"Ya hay {len(t.entregas_activas)} entrega(s): " + "; ".join(nombre_entrega(e) for e in t.entregas_activas))
        lineas.append("        (lo nuevo se agrega; para reemplazar, borra la anterior con `nexuscli borrar`)")
    return lineas


def cmd_entregar(nx: Nexus, args, out: Salida) -> None:
    archivos = [Path(a).expanduser() for a in args.archivos]
    for a in archivos:
        if not a.is_file():
            raise SystemExit(f"No existe o no es archivo: {a}")
    t = nx.tarea(args.tarea, args.curso)
    if not t.acepta_archivos:
        raise SystemExit(f"{t.clave} {t.nombre} no acepta archivos" + (" (usa `nexuscli liga`)" if t.acepta_ligas else ""))
    equipo_id, equipo = _modo_equipo(nx, t, args)
    if not out.json:
        print("\n".join(_resumen_tarea(t, equipo)))
        for a in archivos:
            print(f"Sube:   {a.name} ({texto.tamano(a.stat().st_size)})")
    confirmar("¿Entregar? El profesor lo verá en Nexus.", args.si)
    resultados = []
    for a in archivos:
        if not out.json:
            print(f"Subiendo {a.name}…", flush=True)
        resultados.append({"archivo": str(a), **nx.subir_archivo(t, a, equipo_id)})
    entregas = nx.entregas(t)

    def txt():
        print("Listo. Entregas registradas ahora:")
        _imprimir_entregas(entregas)

    out.emitir({"tarea": t.as_dict(), "resultados": resultados, "entregas": entregas}, txt)


def cmd_liga(nx: Nexus, args, out: Salida) -> None:
    t = nx.tarea(args.tarea, args.curso)
    if not t.acepta_ligas:
        raise SystemExit(f"{t.clave} {t.nombre} no acepta ligas (recurso externo); entrega un archivo.")
    equipo_id, equipo = _modo_equipo(nx, t, args)
    titulo = args.titulo or args.url
    if not out.json:
        print("\n".join(_resumen_tarea(t, equipo)))
        print(f"Liga:   {titulo} <{args.url}>")
    confirmar("¿Entregar la liga? El profesor la verá en Nexus.", args.si)
    res = nx.entregar_liga(t, args.url, titulo, equipo_id, embed=args.embed)
    entregas = nx.entregas(t)

    def txt():
        print("Listo. Entregas registradas ahora:")
        _imprimir_entregas(entregas)

    out.emitir({"tarea": t.as_dict(), "resultado": res, "entregas": entregas}, txt)


def cmd_borrar(nx: Nexus, args, out: Salida) -> None:
    t = nx.tarea(args.tarea, args.curso)
    entregas = [e for e in nx.entregas(t) if e.get("Estado", True)]
    if not entregas:
        raise SystemExit(f"{t.clave} {t.nombre} no tiene entregas.")
    if args.entregas:
        ids = {int(x) for x in args.entregas}
        elegidas = [e for e in entregas if e.get("EntregaId") in ids]
        faltan = ids - {e.get("EntregaId") for e in elegidas}
        if faltan:
            raise SystemExit(f"Esas entregas no están en la tarea: {', '.join(map(str, sorted(faltan)))}")
    elif args.todas or len(entregas) == 1:
        elegidas = entregas
    else:
        print(f"{t.clave} {t.nombre} tiene {len(entregas)} entregas; di cuáles (ids) o usa --todas:")
        _imprimir_entregas(entregas)
        raise SystemExit(2)
    if not out.json:
        print(f"Tarea: {t.clave} {t.nombre} ({texto.curso_corto(t.curso)})")
        print("Se borran:")
        _imprimir_entregas(elegidas)
    confirmar("¿Borrar? No se puede deshacer.", args.si)
    resultados = []
    equipo_id = t.equipo_id
    for e in elegidas:
        r = {"entrega_id": e.get("EntregaId"), "respuesta": nx.borrar_entrega(t, e)}
        doc_id = (e.get("Documento") or {}).get("DocumentoId")
        if args.carpeta and e.get("EnEquipo") and doc_id:
            equipo_id = equipo_id or int((nx.equipo(t.curso_id) or {}).get("EquipoId") or 0)
            if equipo_id:
                r["carpeta"] = nx.borrar_archivo_equipo(equipo_id, doc_id)
        resultados.append(r)
    quedan = nx.entregas(t)

    def txt():
        print("Borrado. Entregas que quedan:")
        _imprimir_entregas(quedan)

    out.emitir({"tarea": t.as_dict(), "resultados": resultados, "entregas": quedan}, txt)


def cmd_equipo(nx: Nexus, args, out: Salida) -> None:
    data = []
    for c in nx.cursos_filtrados(args.curso):
        eq = nx.equipo(c.id)
        data.append({"curso": c.nombre, "curso_id": c.id, "equipo": eq})

    def txt():
        for d in data:
            eq = d["equipo"]
            if not eq:
                print(f"{texto.curso_corto(d['curso'])}: sin equipo")
                continue
            print(f"{texto.curso_corto(d['curso'])}: {eq.get('Nombre')} (equipo {eq.get('EquipoId')})")
            for e in eq.get("Estudiantes") or []:
                correo = e.get("CorreoUniversitario") or e.get("CorreoAdicional") or ""
                print(f"  {e.get('NombreUsuario')}  {autor(e)}" + (f"  <{correo}>" if correo else ""))

    out.emitir(data, txt)


def cmd_carpeta(nx: Nexus, args, out: Salida) -> None:
    t = nx.tarea(args.tarea, args.curso)
    equipo_id = t.equipo_id or int((nx.equipo(t.curso_id) or {}).get("EquipoId") or 0)
    if not equipo_id:
        raise SystemExit("No tienes equipo en ese curso.")
    j = nx.archivos_equipo(t, equipo_id)
    externos = nx.c.call("Equipo/ConsultarRecursosExternos", {
        "EquipoId": equipo_id, "ElementoId": t.id, "TipoElementoId": t.tipo,
    }).get("EquipoRecursoExterno") or []

    def txt():
        print(f"Carpeta del equipo {equipo_id} para {t.clave} {t.nombre}")
        for c in j.get("Carpetas") or []:
            print(f"  [carpeta {c.get('CarpetaId')}] {c.get('Nombre')}")
        docs = documentos_en(j.get("Archivos"))
        for d in docs:
            print(f"  {d['DocumentoId']}  {d.get('Nombre')} ({texto.tamano(d.get('Peso'))}) · {texto.fmt_fecha(texto.fecha(d.get('FechaCreacion')))}")
        for x in externos:
            print(f"  [liga {x.get('ExternoId')}] {x.get('Titulo')} <{x.get('Contenido')}>")
        if not (j.get("Carpetas") or docs or externos):
            print("  (vacía)")

    out.emitir({"tarea": t.as_dict(), "carpeta": j, "externos": externos}, txt)


def cmd_calificaciones(nx: Nexus, args, out: Salida) -> None:
    data = []
    for c in nx.cursos_filtrados(args.curso):
        tareas = nx.tareas(c)
        puntos = sum((t.calificacion or 0) * (t.valor or 0) / 100 for t in tareas if t.calificacion is not None)
        evaluado = sum(t.valor or 0 for t in tareas if t.calificacion is not None)
        total = sum(t.valor or 0 for t in tareas)
        data.append({"curso": c.nombre, "curso_id": c.id, "puntos": round(puntos, 2), "evaluado": evaluado,
                     "total": total, "tareas": [t.as_dict() for t in tareas]})

    def txt():
        for d in data:
            print(f"{d['curso']}: {d['puntos']:g} de {d['evaluado']:g} pts evaluados ({d['total']:g} en total)")
            filas = []
            for t in d["tareas"]:
                cal = t["calificacion"]
                pts = f"{round(cal * (t['valor'] or 0) / 100, 2):g}" if cal is not None else "-"
                filas.append([t["clave"], f"{round(cal, 1):g}" if cal is not None else "-", f"{t['valor']:g}", pts,
                              "sí" if t["retroalimentaciones"] else "", texto.recortar(t["nombre"], 55)])
            tabla(filas, ["#", "CAL", "VALOR", "PTS", "COM", "TAREA"])
            print()

    out.emitir(data, txt)


def cmd_comentarios(nx: Nexus, args, out: Salida) -> None:
    if args.tarea:
        tareas = [nx.tarea(args.tarea, args.curso)]
    else:
        tareas = nx.todas_las_tareas(args.curso)
    items = []
    for t in tareas:
        for r in t.retros:
            items.append({"tarea": t.as_dict() | {"entregas": None, "retroalimentaciones": None}, "retro": r})
    items.sort(key=lambda x: x["retro"].get("FechaModificacion") or "", reverse=True)

    def txt():
        if not items:
            print("Sin comentarios del profesor.")
            return
        for it in items:
            t = it["tarea"]
            _imprimir_retro(it["retro"], f"{t['clave']} {texto.recortar(t['nombre'], 40)} ({texto.curso_corto(t['curso'])})")
            print()

    out.emitir(items, txt)


def cmd_responder(nx: Nexus, args, out: Salida) -> None:
    objetivo = None
    for t in nx.todas_las_tareas(args.curso):
        for r in t.retros:
            if r.get("RetroalimentacionId") == args.retro:
                objetivo = (t, r)
    if not objetivo:
        raise SystemExit(f"No encontré el comentario {args.retro}. Míralos con `nexuscli comentarios`.")
    t, r = objetivo
    if not r.get("DerechoReplica"):
        raise SystemExit("Ese comentario no admite respuesta (el profesor no habilitó derecho de réplica).")
    if not out.json:
        print(f"Respuesta a [{args.retro}] en {t.clave} {t.nombre}:\n{indent(args.texto)}")
    confirmar("¿Enviar respuesta? La verá el profesor.", args.si)
    res = nx.responder_retro(t.curso_id, args.retro, args.texto)
    out.emitir(res, lambda: print("Enviada."))


def cmd_avisos(nx: Nexus, args, out: Salida) -> None:
    data = []
    for c in nx.cursos_filtrados(args.curso):
        for a in nx.avisos(c.id):
            data.append({"curso": c.nombre, **a})
    data.sort(key=lambda a: a.get("FechaInicio") or "", reverse=True)

    def txt():
        if not data:
            print("Sin avisos.")
        for a in data:
            urg = " · URGENTE" if a.get("EsUrgente") else ""
            print(f"[{a.get('AvisoId')}] {a.get('Titulo')} · {texto.curso_corto(a['curso'])}{urg}")
            print(f"    {texto.fmt_fecha(texto.fecha(a.get('FechaInicio')), False)} a {texto.fmt_fecha(texto.fecha(a.get('FechaFin')), False)}")
            print(indent(texto.html_a_texto(a.get("Mensaje")), 4))
            print()

    out.emitir(data, txt)


_TIPOS_RECURSO = {
    "RecursoArchivos": "archivo", "RecursosWeb": "web", "RecursosExternos": "externo", "RecursosLibros": "libro",
    "RecursosArticulos": "artículo", "RecursosTextos": "texto", "RecursosHTML": "html", "RecursoScorm": "scorm",
}


def cmd_recursos(nx: Nexus, args, out: Salida) -> None:
    data = []
    for c in nx.cursos_filtrados(args.curso):
        rec = nx.recursos(c.id)
        for clave, tipo in _TIPOS_RECURSO.items():
            for r in rec.get(clave) or []:
                if r.get("MostrarEstudiante") is False and not args.todos:
                    continue
                data.append({"curso": c.nombre, "tipo": tipo, **r})

    varios = len({r["curso"] for r in data}) > 1

    def txt():
        if not data:
            print("Sin recursos visibles.")
        for r in data:
            doc = r.get("Documento") or {}
            titulo = r.get("Titulo") or r.get("Nombre") or doc.get("Nombre") or "?"
            linea = f"{r['tipo']:<8} {titulo.strip()}"
            if doc.get("DocumentoId"):
                linea += f"  (doc {doc['DocumentoId']}, {texto.tamano(doc.get('Peso'))})"
            url = r.get("URL") or r.get("Url") or r.get("Liga")
            if url:
                linea += f"  <{url}>"
            print(f"{texto.recortar(texto.curso_corto(r['curso']), 22):<22}  {linea}" if varios else linea)
            if args.largo and r.get("Contenido"):
                print(indent(texto.html_a_texto(r.get("Contenido")), 4))

    out.emitir(data, txt)


def cmd_descargar(nx: Nexus, args, out: Salida) -> None:
    buscados = {int(x) for x in args.documentos}
    encontrados: dict[int, dict] = {}
    for c in nx.cursos_filtrados(args.curso):
        for d in documentos_en(nx.recursos(c.id)) + documentos_en(nx.portafolio(c.id)):
            if d["DocumentoId"] in buscados:
                encontrados[d["DocumentoId"]] = d
        if buscados <= encontrados.keys():
            break
    faltan = buscados - encontrados.keys()
    if faltan:
        raise SystemExit(f"No encontré estos documentos: {', '.join(map(str, sorted(faltan)))}")
    destino = Path(args.salida).expanduser()
    rutas = []
    for d in encontrados.values():
        nombre = Path(d.get("Nombre") or f"{d['DocumentoId']}{d.get('Extension') or ''}").name
        ruta = destino / nombre
        n = 1
        while ruta.exists():
            ruta = destino / f"{Path(nombre).stem} ({n}){Path(nombre).suffix}"
            n += 1
        nx.c.descargar(d["URL"], ruta)
        rutas.append(str(ruta))
    out.emitir(rutas, lambda: [print(f"Guardado: {r}") for r in rutas])


def cmd_foro(nx: Nexus, args, out: Salida) -> None:
    if args.tema:
        c = nx.curso(args.curso) if args.curso else None
        curso_id = c.id if c else _curso_de_tema(nx, args.tema)
        tema = nx.foro_tema(curso_id, args.tema)

        def txt():
            print(f"{tema.get('Nombre')}  (tema {tema.get('TemaId')})")
            print(indent(texto.html_a_texto(tema.get("Mensaje")), 2))
            print()
            _imprimir_comentarios(tema.get("Comentarios") or [], 0)

        out.emitir(tema, txt)
        return
    data = []
    for c in nx.cursos_filtrados(args.curso):
        for t in nx.foro_temas(c.id):
            data.append({"curso": c.nombre, "curso_id": c.id, **t})

    def txt():
        if not data:
            print("Sin temas de foro.")
        filas = [[t.get("TemaId"), texto.recortar(texto.curso_corto(t["curso"]), 22),
                  texto.fmt_fecha(texto.fecha(t.get("FechaFin")), False), texto.recortar(t.get("Nombre") or "", 60)]
                 for t in data]
        tabla(filas, ["TEMA", "CURSO", "CIERRA", "NOMBRE"])

    out.emitir(data, txt)


def _curso_de_tema(nx: Nexus, tema_id: int) -> int:
    for c in nx.cursos():
        if any(t.get("TemaId") == tema_id for t in nx.foro_temas(c.id)):
            return c.id
    raise SystemExit(f"No encontré el tema {tema_id}; pasa -c CURSO.")


def _imprimir_comentarios(comentarios: list[dict], nivel: int) -> None:
    if not comentarios and nivel == 0:
        print("  (sin comentarios)")
    for c in comentarios:
        if c.get("Estado") is False or c.get("Oculto"):
            continue
        quien = autor(c.get("Cuenta") or c.get("Persona"))
        fecha = texto.fmt_fecha(texto.fecha(c.get("FechaCreacion")))
        pad = "  " * (nivel + 1)
        print(f"{pad}[{c.get('TemaComentarioId')}] {quien} · {fecha}")
        print(indent(texto.html_a_texto(c.get("Comentario")), len(pad) + 2))
        _imprimir_comentarios((c.get("Respuestas") or []) + (c.get("ComentariosHijos") or []), nivel + 1)


def cmd_comentar(nx: Nexus, args, out: Salida) -> None:
    if not out.json:
        print(f"Comentario en el tema {args.tema}" + (f" (respuesta a {args.responde_a})" if args.responde_a else "") + ":")
        print(indent(args.texto))
    confirmar("¿Publicar en el foro? Lo verá todo el grupo.", args.si)
    res = nx.foro_comentar(args.tema, args.texto, args.responde_a or 0)
    out.emitir(res, lambda: print("Publicado."))


def cmd_mensajes(nx: Nexus, args, out: Salida) -> None:
    if args.conversacion:
        j = nx.mensajes(args.conversacion)
        conv = j.get("Conversacion") or j
        mensajes = conv.get("Mensajes") or j.get("Mensajes") or []

        def txt():
            print(f"{conv.get('Nombre') or 'Conversación'} ({args.conversacion})")
            for m in mensajes:
                quien = autor(m.get("Emisor") or m.get("Cuenta")) if (m.get("Emisor") or m.get("Cuenta")) else f"cuenta {m.get('EmisorCuentaId')}"
                print(f"  {texto.fmt_fecha(texto.fecha(m.get('FechaCreacion')))} · {quien}")
                print(indent(texto.html_a_texto(m.get("Mensaje")), 4))

        out.emitir(j, txt)
        return
    data = []
    for c in nx.cursos_filtrados(args.curso):
        for conv in nx.conversaciones(c.id):
            data.append({"curso": c.nombre, **conv})

    def txt():
        if not data:
            print("Sin conversaciones.")
        for conv in data:
            print(f"[{conv.get('ConversacionId')}] {conv.get('Nombre')} · {texto.curso_corto(conv['curso'])}")

    out.emitir(data, txt)


def cmd_enviar(nx: Nexus, args, out: Salida) -> None:
    if not out.json:
        print(f"Mensaje a la conversación {args.conversacion}:\n{indent(args.texto)}")
    confirmar("¿Enviar?", args.si)
    res = nx.enviar_mensaje(args.conversacion, args.texto)
    out.emitir(res, lambda: print("Enviado."))


def cmd_escribir(nx: Nexus, args, out: Salida) -> None:
    c = nx.curso(args.curso)
    profes = c.profesores
    if not profes:
        raise SystemExit("Ese curso no tiene profesor registrado.")
    asunto = args.asunto or texto.recortar(args.texto, 40)
    if not out.json:
        print(f"Nueva conversación con {', '.join(autor(p) for p in profes)} en {c.nombre}")
        print(f"Asunto: {asunto}\n{indent(args.texto)}")
    confirmar("¿Enviar al profesor?", args.si)
    conv = nx.nueva_conversacion(c.id, asunto, profes)
    conv_id = (conv.get("Conversacion") or {}).get("ConversacionId")
    if not conv_id:
        raise NexusError(f"Nexus no devolvió la conversación creada: {texto.recortar(json.dumps(conv, ensure_ascii=False), 200)}")
    res = nx.enviar_mensaje(conv_id, args.texto)
    out.emitir({"conversacion": conv, "mensaje": res}, lambda: print(f"Enviado (conversación {conv_id})."))


def _recolectar(nx: Nexus, c, sin_foro: bool) -> list[tuple[str, str, dict]]:
    """Todo lo observable de una materia: (clave estable, huella del contenido, item)."""
    regs: list[tuple[str, str, dict]] = []
    corto = nx.corto(c.id, c.nombre)

    def reg(clave: str, h: str, item: dict) -> None:
        regs.append((clave, h, item))

    for t in nx.tareas(c):
        base = {"curso": corto, "curso_id": c.id, "clave": t.clave, "tarea": t.nombre, "tarea_id": t.id}
        reg(f"tarea:{c.id}:{t.tipo}:{t.id}", huella(t.fin, t.limite, t.valor),
            {**base, "tipo": "tarea", "texto": f"cierra {texto.fmt_fecha(t.cierre)} · {t.valor:g} pts",
             "cierre": t.cierre.isoformat() if t.cierre else None})
        if t.calificacion is not None:
            reg(f"calif:{c.id}:{t.tipo}:{t.id}", huella(t.calificacion),
                {**base, "tipo": "calificación", "texto": f"{t.calificacion:g}"})
        for r in t.retros:
            reps = [rep.get("Comentario") for rep in r.get("Replicas") or []]
            reg(f"retro:{r.get('RetroalimentacionId')}", huella(r.get("Descripcion"), reps),
                {**base, "tipo": "comentario", "id": r.get("RetroalimentacionId"),
                 "texto": texto.html_a_texto(r.get("Descripcion")), "replicas": reps})
        for e in t.entregas:
            reg(f"entrega:{e.get('EntregaId')}", huella(e.get("Estado")),
                {**base, "tipo": "entrega", "texto": nombre_entrega(e)})
    for a in nx.avisos(c.id):
        reg(f"aviso:{a.get('AvisoId')}", huella(a.get("Titulo"), a.get("Mensaje"), a.get("FechaFin")),
            {"curso": corto, "curso_id": c.id, "tipo": "aviso", "id": a.get("AvisoId"), "tarea": a.get("Titulo"),
             "texto": texto.html_a_texto(a.get("Mensaje"))})
    if sin_foro:
        return regs
    ahora = texto.ahora()
    for tema in nx.foro_temas(c.id):
        reg(f"tema:{tema.get('TemaId')}", huella(tema.get("Nombre")),
            {"curso": corto, "curso_id": c.id, "tipo": "tema de foro", "id": tema.get("TemaId"),
             "tarea": tema.get("Nombre"), "texto": ""})
        ini, fin = texto.fecha(tema.get("FechaInicio")), texto.fecha(tema.get("FechaFin"))
        if ini and fin and ini <= ahora <= fin:
            for com in _aplanar(nx.foro_tema(c.id, tema["TemaId"]).get("Comentarios") or []):
                reg(f"foro:{com.get('TemaComentarioId')}", huella(com.get("Comentario")),
                    {"curso": corto, "curso_id": c.id, "tipo": "foro", "id": com.get("TemaComentarioId"),
                     "tema_id": tema.get("TemaId"), "tarea": tema.get("Nombre"), "autor": autor(com.get("Cuenta")),
                     "texto": texto.html_a_texto(com.get("Comentario"))})
    for conv in nx.conversaciones(c.id):
        resumen = {k: conv.get(k) for k in ("Nombre", "FechaModificacion", "UltimoMensaje", "Mensajes", "NoLeidos") if k in conv}
        reg(f"conv:{conv.get('ConversacionId')}", huella(resumen),
            {"curso": corto, "curso_id": c.id, "tipo": "mensaje", "id": conv.get("ConversacionId"),
             "tarea": conv.get("Nombre"), "texto": ""})
    return regs


def clasificar_novedades(visto: Visto, por_curso: list[tuple[Any, list]], todo: bool = False) -> dict:
    """Decide qué se enseña. La primera vez (base vacía) todo se registra en silencio; una
    materia que nunca se había visto también, y solo se anuncia con una línea."""
    primera = visto.vacio()
    hallazgos: list[dict] = []
    marcas: list[tuple[str, str]] = []
    nuevas: list[dict] = []
    for c, regs in por_curso:
        marcas += [(k, h) for k, h, _ in regs]
        conocida = visto.materia_conocida(c.id)
        if (primera or not conocida) and not todo:
            if not primera:
                tareas = [it for _k, _h, it in regs if it["tipo"] == "tarea"]
                proximas = sorted(it["cierre"] for it in tareas if it.get("cierre") and it["cierre"] >= texto.ahora().isoformat())
                resumen = f"{len(tareas)} tareas"
                if proximas:
                    resumen += f"; la primera cierra {texto.fmt_fecha(texto.fecha(proximas[0]))}"
                nuevas.append({"estado": "nuevo", "tipo": "materia nueva", "curso": c.nombre, "curso_id": c.id,
                               "tarea": c.nombre, "texto": resumen + ". Lo demás quedó registrado como visto."})
            continue
        for k, h, item in regs:
            estado = visto.estado(k, h)
            if estado:
                hallazgos.append({"estado": estado, **item})
    return {"primera": primera and not todo, "hallazgos": nuevas + hallazgos, "marcas": marcas,
            "materias": [(c.id, c.nombre) for c, _ in por_curso]}


COLOR_NOVEDAD = {"cierre": "rojo", "materia nueva": "hueso", "comentario": "vino", "calificación": "oliva",
                 "calificación final": "oliva", "aviso": "naranja", "foro": "hueso", "mensaje": "hueso",
                 "afi": "oliva", "afi nueva": "naranja", "siase": "hueso"}


def cmd_novedades(nx: Nexus, args, out: Salida) -> None:
    visto = Visto(nx.c.state / "visto.db")
    cursos = nx.cursos_filtrados(args.curso)
    por_curso = [(c, _recolectar(nx, c, args.sin_foro)) for c in cursos]
    r = clasificar_novedades(visto, por_curso, todo=args.todo)
    if not args.no_marcar:
        visto.marcar(r["marcas"])
        visto.conocer(r["materias"])
    de_siase: list[dict] = []
    if args.siase and not args.no_marcar:
        from .cli_siase import novedades_siase
        de_siase = novedades_siase(nx, visto)
    visto.close()
    cierres = [{"estado": "aviso", "tipo": "cierre", "curso": a.curso, "curso_id": a.curso_id, "tarea": a.curso,
                "texto": f"{a.texto}.\n{a.comando}"}
               for a in avisos_de_cierre(cursos, nx.materias, nx.c.state)]

    if r["primera"]:
        out.emitir({"primera_vez": True, "registrados": len(r["marcas"]), "cierres": cierres}, lambda: (
            print(f"Primera vez: registré {len(r['marcas'])} cosas como ya vistas. Desde ahora `nexuscli novedades` "
                  "te enseña solo lo nuevo (usa --todo para ver todo, o `nexuscli comentarios`)."),
            [print(f"[cierre] {x['texto']}") for x in cierres],
            [print(f"[{x['tipo']}] {x['texto']}") for x in de_siase]))
        return
    hallazgos = cierres + de_siase + r["hallazgos"]
    usados = set(nx.materias.codigos.values())
    for h in hallazgos:
        if h["tipo"] != "materia nueva":
            continue
        cod = nx.materias.codigo(h["curso_id"])
        if cod:
            h["texto"] += f"\nMírala con `nexuscli tareas -c {cod}`."
        else:
            prop = proponer_codigo(nx, h["curso"], usados)
            usados.add(prop)
            h["texto"] += (f"\nMírala con `nexuscli tareas -c {h['curso_id']}` y dale código: "
                           f"`nexuscli codigo {h['curso_id']} {prop}`.")

    def txt():
        if not hallazgos:
            print("Nada nuevo.")
            return
        orden = ["cierre", "materia nueva", "siase", "comentario", "calificación", "calificación final", "aviso", "foro",
                 "mensaje", "afi", "afi nueva", "tarea", "entrega", "tema de foro"]
        hallazgos.sort(key=lambda h: (orden.index(h["tipo"]) if h["tipo"] in orden else 99, h["curso"]))
        for h in hallazgos:
            etiqueta = pintar("[" + h["tipo"] + (" (cambió)" if h["estado"] == "cambio" else "") + "]",
                              COLOR_NOVEDAD.get(h["tipo"], "tenue"), negrita=True)
            if h["tipo"] in ("cierre", "materia nueva", "siase"):
                print(f"{etiqueta} {h['curso']}")
                print(indent(h["texto"], 4))
                continue
            quien = f"{h['clave']} {h['tarea']}" if h.get("clave") else (h.get("tarea") or "")
            print(f"{etiqueta} {pintar(h['curso'], 'hueso')} · {texto.recortar(quien, 70)}")
            if h.get("autor"):
                print(f"    de {h['autor']}")
            if h.get("texto"):
                print(indent(h["texto"] if h["tipo"] in ("comentario", "aviso", "foro") else texto.recortar(h["texto"], 100), 4))

    out.emitir(hallazgos, txt)


def _aplanar(comentarios: list[dict]) -> list[dict]:
    out = []
    for c in comentarios:
        out.append(c)
        out.extend(_aplanar((c.get("Respuestas") or []) + (c.get("ComentariosHijos") or [])))
    return out


def cmd_clonar(nx: Nexus, args, out: Salida) -> None:
    from .clonar import Clonador, dueno

    raiz = Path(args.salida).expanduser()
    solo = nx.tarea(args.tarea, args.curso) if args.tarea else None
    if solo:
        cursos = [c for c in nx.cursos() if c.id == solo.curso_id]
    else:
        cursos = nx.cursos_filtrados(args.curso)
    if args.como and len(cursos) > 1:
        raise SystemExit("--como es para un solo curso; agrega -c CURSO.")
    # Cada materia necesita nombre de carpeta: --como, o su código.
    usados = set(nx.materias.codigos.values())
    sin_codigo = [c for c in cursos if not (args.como or nx.materias.codigo(c.id))]
    if sin_codigo:
        lineas = []
        for c in sin_codigo:
            prop = proponer_codigo(nx, c.nombre, usados)
            usados.add(prop)
            lineas.append(f"  nexuscli codigo {c.id} {prop}    # {c.nombre}")
        raise SystemExit("Estas materias no tienen código, que es el nombre de su carpeta. Asígnalo (la propuesta "
                         "sale de su nombre) o usa --como:\n" + "\n".join(lineas))
    planes = []
    for c in cursos:
        nombre = args.como or nx.materias.codigo(c.id)
        destino = raiz / nombre
        otro = dueno(destino)
        if otro and otro[0] != c.id:
            raise SystemExit(f"{destino} ya es el clon de {otro[1]} (curso {otro[0]}), no de {c.nombre}. "
                             "Usa otra carpeta con --como o cambia el código con `nexuscli codigo`.")
        planes.append((c, nombre, destino))
    log = (lambda _m: None) if out.json else print
    resumenes = []
    for c, nombre, destino in planes:
        banderas = "".join(f" --{b}" for b in ("personal", "ocultos") if getattr(args, b))
        banderas += " --sin-archivos" if args.sin_archivos else ""
        cod = nx.materias.codigo(c.id)
        comando = f"nexuscli clonar -c {cod or c.id} -o {args.salida}" + ("" if nombre == cod else f" --como {nombre}") + banderas
        log(f"{c.nombre} → {destino}" + (f" (solo {solo.clave})" if solo else ""))
        cl = Clonador(nx, destino, archivos=not args.sin_archivos, personal=args.personal, ocultos=args.ocultos, log=log)
        r = cl.curso(c, solo=solo, comando=None if solo else comando)
        if not solo and not r.errores:
            registrar_clon(nx.c.state, c.id, c.nombre, destino)
        resumenes.append({"curso": c.nombre, "destino": str(destino), **r.as_dict()})
        if not out.json:
            partes = [
                f"{r.actividades} actividades",
                f"{len(r.bajados)} archivos bajados ({texto.tamano(r.bytes)})" if r.bajados else "nada nuevo que bajar",
            ]
            if r.copiados:
                partes.append(f"{len(r.copiados)} copiados de otra carpeta")
            if r.sin_cambio:
                partes.append(f"{r.sin_cambio} ya estaban al día")
            partes.append(f"{len(r.escritos)} .md actualizados" if r.escritos else "los .md ya estaban al día")
            print(pintar("Listo: ", "oliva", negrita=True) + " · ".join(partes))
            for d in r.desaparecidos:
                print(f"  ya no está en Nexus (se conserva): {d}")
            for e in r.errores:
                print(f"  ✗ {e}", file=sys.stderr)
            print()
    if out.json:
        out.emitir(resumenes, lambda: None)
    if any(r["errores"] for r in resumenes):
        raise SystemExit(1)


def cmd_api(nx: Nexus, args, out: Salida) -> None:
    endpoint = args.endpoint.strip("/")
    body_raw = args.json or "{}"
    if body_raw.startswith("@"):
        body_raw = Path(body_raw[1:]).expanduser().read_text(encoding="utf-8")
    body = json.loads(body_raw)
    metodo = endpoint.split("/")[-1]
    if not metodo.startswith("Consultar"):
        if not args.escribir:
            raise SystemExit(f"{endpoint} no es de lectura (Consultar*). Si de verdad quieres llamarlo, agrega --escribir.")
        print(f"POST {endpoint} {json.dumps(body, ensure_ascii=False)}")
        confirmar("¿Mandar esta llamada que modifica Nexus?", args.si)
    j = nx.c.call(endpoint, body)
    j.pop("Sesion", None)
    print(json.dumps(j, ensure_ascii=False, indent=2))


def _ts(epoch: float):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.fromtimestamp(epoch, ZoneInfo(config.TZ)).replace(tzinfo=None)


# ---------------------------------------------------------------------- argparse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nexuscli",
        description="Nexus UANL desde la terminal: tareas, entregas (individual y en equipo), "
                    "calificaciones, comentarios, avisos, foro y mensajes.",
        epilog="Ejemplos:\n"
               "  nexuscli tareas --pendientes\n"
               "  nexuscli tarea 2.3 -c analisis\n"
               "  nexuscli entregar 'pitch' pitch_final.pdf -c narrativa\n"
               "  nexuscli novedades\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"nexuscli {__version__}")
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--json", action="store_true", help="salida JSON (para scripts y agentes)")
    comun.add_argument("--pace", choices=list(PERFILES), default=os.environ.get("NEXUS_PACE", "normal"),
                       help="pausas aleatorias entre llamadas (default: normal, o $NEXUS_PACE)")
    comun.add_argument("--fresco", action="store_true", help="ignora la caché local de cursos y estructura")
    comun.add_argument("-v", "--verbose", action="store_true", help="muestra cada llamada")
    sub = p.add_subparsers(dest="cmd", metavar="COMANDO", required=True)

    def add(nombre: str, fn, ayuda: str, curso: bool = False, si: bool = False, **kw) -> argparse.ArgumentParser:
        sp = sub.add_parser(nombre, parents=[comun], help=ayuda, description=ayuda, **kw)
        if curso:
            sp.add_argument("-c", "--curso", help="curso (parte del nombre o id)")
        if si:
            sp.add_argument("-y", "--si", action="store_true", help="no preguntar confirmación")
        sp.set_defaults(fn=fn)
        return sp

    add("login", cmd_login, "entra a Nexus y guarda la sesión")
    add("logout", cmd_logout, "cierra la sesión y la borra de este equipo")
    add("doctor", cmd_doctor, "revisa credenciales, sesión y acceso al API")
    add("cursos", cmd_cursos, "lista tus cursos con su código y su último clon")
    sp = add("codigo", cmd_codigo, "códigos cortos de materia (anau, crng): se usan en -c y como carpeta de clonar")
    sp.add_argument("curso", nargs="?", help="materia (parte del nombre, id o código); sin nada lista todos")
    sp.add_argument("codigo", nargs="?", help="código nuevo para esa materia")
    sp.add_argument("--quitar", action="store_true", help="quita el código de esa materia")
    sp.add_argument("--aceptar", action="store_true", help="asigna la propuesta a todas las materias sin código")

    sp = add("tareas", cmd_tareas, "tareas con estado, cierre y valor", curso=True)
    sp.add_argument("-p", "--pendientes", action="store_true", help="solo las que faltan por entregar")
    sp.add_argument("-s", "--semana", action="store_true", help="solo las que cierran en los próximos 7 días")

    sp = add("tarea", cmd_tarea, "detalle de una tarea: instrucciones, entregas y comentarios", curso=True)
    sp.add_argument("tarea", help="número (2.3, PIA), id o parte del nombre")

    sp = add("entregas", cmd_entregas, "entregas registradas de una tarea", curso=True)
    sp.add_argument("tarea")

    sp = add("entregar", cmd_entregar, "sube archivo(s) como entrega; en tareas de equipo entrega por el equipo",
             curso=True, si=True)
    sp.add_argument("tarea")
    sp.add_argument("archivos", nargs="+", metavar="ARCHIVO")
    sp.add_argument("--individual", action="store_true", help="en tarea de equipo, entregar solo a tu nombre")
    sp.add_argument("--equipo", action="store_true", help="forzar entrega en equipo")

    sp = add("liga", cmd_liga, "entrega una liga (recurso externo)", curso=True, si=True)
    sp.add_argument("tarea")
    sp.add_argument("url")
    sp.add_argument("-t", "--titulo", help="título visible (default: la URL)")
    sp.add_argument("--embed", action="store_true", help="tipo Embed en vez de URL")
    sp.add_argument("--individual", action="store_true")
    sp.add_argument("--equipo", action="store_true")

    sp = add("borrar", cmd_borrar, "borra entrega(s) de una tarea", curso=True, si=True)
    sp.add_argument("tarea")
    sp.add_argument("entregas", nargs="*", metavar="ENTREGA_ID")
    sp.add_argument("--todas", action="store_true", help="borra todas las entregas de la tarea")
    sp.add_argument("--carpeta", action="store_true", help="en entregas de equipo, borra también el archivo de la carpeta del equipo")

    add("equipo", cmd_equipo, "tu equipo en cada curso", curso=True)
    sp = add("carpeta", cmd_carpeta, "archivos en la carpeta del equipo para una tarea", curso=True)
    sp.add_argument("tarea")

    add("calificaciones", cmd_calificaciones, "calificaciones por curso", curso=True)

    sp = add("comentarios", cmd_comentarios, "comentarios (retroalimentación) del profesor", curso=True)
    sp.add_argument("tarea", nargs="?")

    sp = add("responder", cmd_responder, "responde un comentario del profesor (derecho de réplica)", curso=True, si=True)
    sp.add_argument("retro", type=int, metavar="COMENTARIO_ID")
    sp.add_argument("texto")

    add("avisos", cmd_avisos, "avisos de los cursos", curso=True)

    sp = add("recursos", cmd_recursos, "recursos del curso (archivos, ligas, lecturas)", curso=True)
    sp.add_argument("--todos", action="store_true", help="incluye los que Nexus no le muestra al estudiante")
    sp.add_argument("-l", "--largo", action="store_true", help="muestra el contenido de los recursos de texto")

    sp = add("descargar", cmd_descargar, "baja documentos por id (de recursos, entregas o comentarios)", curso=True)
    sp.add_argument("documentos", nargs="+", metavar="DOC_ID")
    sp.add_argument("-o", "--salida", default=".", help="carpeta destino (default: la actual)")

    sp = add("foro", cmd_foro, "temas del foro, o los comentarios de un tema", curso=True)
    sp.add_argument("tema", nargs="?", type=int, metavar="TEMA_ID")

    sp = add("comentar", cmd_comentar, "publica en un tema del foro", si=True)
    sp.add_argument("tema", type=int, metavar="TEMA_ID")
    sp.add_argument("texto")
    sp.add_argument("--responde-a", type=int, metavar="COMENTARIO_ID")

    sp = add("mensajes", cmd_mensajes, "conversaciones privadas, o los mensajes de una", curso=True)
    sp.add_argument("conversacion", nargs="?", type=int, metavar="CONVERSACION_ID")

    sp = add("enviar", cmd_enviar, "manda un mensaje a una conversación existente", si=True)
    sp.add_argument("conversacion", type=int, metavar="CONVERSACION_ID")
    sp.add_argument("texto")

    sp = add("escribir", cmd_escribir, "abre conversación nueva con el profesor de un curso", curso=True, si=True)
    sp.add_argument("texto")
    sp.add_argument("--asunto")

    sp = add("novedades", cmd_novedades, "lo nuevo desde la última vez: comentarios, calificaciones, avisos, foro...",
             curso=True)
    sp.add_argument("--no-marcar", action="store_true", help="solo mirar; no marcar como visto")
    sp.add_argument("--todo", action="store_true", help="la primera vez, enseñar todo en lugar de solo registrar")
    sp.add_argument("--sin-foro", action="store_true", help="no revisar foro ni mensajes (más rápido)")
    sp.add_argument("--siase", action="store_true",
                    help="suma SIASE: calificaciones finales, asistencia a AFIs y AFIs nuevas con cupo")

    sp = add("clonar", cmd_clonar,
             "copia local de las tareas: instrucciones, rúbrica y recursos (y con --personal tus calificaciones)",
             curso=True)
    sp.add_argument("tarea", nargs="?", help="solo esta actividad (default: todas las del curso)")
    sp.add_argument("-o", "--salida", default=".", help="carpeta raíz; cada curso va en su propia subcarpeta")
    sp.add_argument("--como", metavar="NOMBRE", help="nombre de la carpeta del curso (default: su código, ver `nexuscli codigo`)")
    sp.add_argument("--sin-archivos", action="store_true", help="solo los .md, sin bajar archivos ni imágenes")
    sp.add_argument("--personal", action="store_true", help="agrega calificación, rúbrica marcada, comentarios y tus entregas")
    sp.add_argument("--ocultos", action="store_true", help="incluye recursos que Nexus no le muestra al estudiante")

    from . import cli_siase as cs
    sp_siase = sub.add_parser("siase", help="SIASE: AFIs con cupo, historial de AFIs, kardex, calificaciones y horario",
                              description="SIASE: AFIs con cupo, historial de AFIs, kardex, calificaciones y horario.")
    ss = sp_siase.add_subparsers(dest="siase_cmd", metavar="COMANDO", required=True)

    def add_s(nombre: str, fn, ayuda: str, si: bool = False) -> argparse.ArgumentParser:
        p_ = ss.add_parser(nombre, parents=[comun], help=ayuda, description=ayuda)
        p_.add_argument("--carrera", help="si tienes varias carreras en SIASE: parte de su nombre")
        if si:
            p_.add_argument("-y", "--si", action="store_true", help="no preguntar confirmación")
        p_.set_defaults(fn=fn)
        return p_

    add_s("perfil", cs.cmd_perfil, "tu matrícula, nombre, carrera y plan")
    sp = add_s("afis", cs.cmd_afis, "AFIs del mes con su cupo")
    sp.add_argument("-m", "--mes", help="mes (número o nombre); default: el que enseña SIASE")
    sp.add_argument("-a", "--area", help="área: culturales, artísticas, deportivas, académicas...")
    sp.add_argument("-d", "--con-cupo", action="store_true", help="solo las que tienen lugares")
    sp.add_argument("-b", "--buscar", help="texto en el nombre, descripción u organizador")
    sp.add_argument("-s", "--semana", action="store_true", help="solo las de los próximos 7 días")
    sp.add_argument("-l", "--largo", action="store_true", help="con la descripción de cada una")
    sp.add_argument("--pasadas", action="store_true", help="incluye las que ya terminaron")
    sp.add_argument("--nuevas", action="store_true", help="solo las que no habías visto")
    sp = add_s("afi", cs.cmd_afi, "detalle de una AFI: descripción, cupo, lugar y si estás pre-registrado")
    sp.add_argument("id", type=int)
    sp.add_argument("-m", "--mes")
    add_s("historial", cs.cmd_historial, "tus AFIs: cuántas oficiales llevas de cuántas y cada evento")
    sp = add_s("inscribir", cs.cmd_inscribir, "pre-regístrate en una AFI (pide confirmación)", si=True)
    sp.add_argument("id", type=int)
    sp.add_argument("-m", "--mes")
    sp = add_s("liberar", cs.cmd_liberar, "libera tu lugar en una AFI en la que estás pre-registrado", si=True)
    sp.add_argument("id", type=int)
    sp = add_s("kardex", cs.cmd_kardex, "todas tus materias con sus oportunidades")
    sp.add_argument("-s", "--semestre", type=int)
    sp.add_argument("-p", "--pendientes", action="store_true", help="solo las que no has aprobado")
    add_s("periodos", cs.cmd_periodos, "periodos escolares para calificaciones y horario")
    sp = add_s("calificaciones", cs.cmd_calificaciones, "calificaciones finales de un periodo")
    sp.add_argument("-p", "--periodo", help="número de `periodos` o parte del nombre (default: el actual)")
    sp = add_s("horario", cs.cmd_horario, "tu horario de clases de un periodo")
    sp.add_argument("-p", "--periodo", help="número de `periodos` o parte del nombre (default: el actual)")
    sp.add_argument("-l", "--lista", action="store_true", help="por día en lugar de cuadrícula")

    sp = add("api", cmd_api, "llamada directa a WebApi/<Dominio>/<Método> (lectura; --escribir para lo demás)", si=True)
    sp.add_argument("endpoint", help="p. ej. Curso/ConsultarDetalleCurso")
    sp.add_argument("json", nargs="?", help="cuerpo JSON o @archivo.json")
    sp.add_argument("--escribir", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    out = Salida(getattr(args, "json", False))
    client = Client(pacer=Pacer(args.pace), verbose=args.verbose)
    nx = Nexus(client, fresco=args.fresco)
    try:
        args.fn(nx, args, out)
    except Ambiguo as e:
        print(f"nexuscli: {e.args[0]}", file=sys.stderr)
        for o in e.opciones:
            print(f"  {o}", file=sys.stderr)
        raise SystemExit(2)
    except (NoEncontrado, LoginError, config.CredencialesError) as e:
        print(f"nexuscli: {e}", file=sys.stderr)
        raise SystemExit(2)
    except SiaseError as e:
        print(f"nexuscli: SIASE: {e}", file=sys.stderr)
        raise SystemExit(1)
    except NexusError as e:
        print(f"nexuscli: Nexus respondió con error: {e}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    finally:
        if args.verbose and client.llamadas:
            print(f"· {client.llamadas} llamadas, {client.pacer.total:.1f} s en pausas", file=sys.stderr)


if __name__ == "__main__":
    main()

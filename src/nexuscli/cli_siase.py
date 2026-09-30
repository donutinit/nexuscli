"""`nexuscli siase ...`: AFIs, historial, kardex, calificaciones y horario de SIASE."""

from __future__ import annotations

import textwrap
from datetime import datetime
from typing import Any

from . import texto
from .estilo import pintar
from .siase import (
    Afi, EventoAfi, Siase, SiaseError, area_desde, dia_nombre, elegir_periodo, mes_desde,
)
from .store import Visto, huella

_COLORES_MATERIA = ["naranja", "oliva", "vino", "hueso", "rojo", "papel"]


def _siase(nx, args) -> Siase:
    return Siase(nx.c, carrera=getattr(args, "carrera", None))


def _tabla(filas, encabezados):
    from .cli import tabla
    tabla(filas, encabezados)


def _confirmar(pregunta, si):
    from .cli import confirmar
    confirmar(pregunta, si)


def _indent(s: str, n: int = 4) -> str:
    from .cli import indent
    return indent(s, n)


# ---------------------------------------------------------------------- formato


def fmt_cuando(a: Afi) -> str:
    if not a.inicio:
        return "-"
    if a.fin and a.fin.date() != a.inicio.date():
        return f"{texto.fmt_fecha(a.inicio, con_hora=False)} → {texto.fmt_fecha(a.fin, con_hora=False)}"
    fin = f"-{a.fin:%H:%M}" if a.fin else ""
    return f"{texto.fmt_fecha(a.inicio)}{fin}"


def fmt_cupo(a: Afi) -> str:
    if a.lleno or not a.disponibles:
        return pintar("lleno", "rojo")
    cap = a.capacidad or 0
    txt = f"{a.disponibles}/{cap}" if cap else str(a.disponibles)
    escaso = a.disponibles < 10 or (cap and a.disponibles / cap < 0.1)
    return pintar(txt, "naranja" if escaso else "oliva")


_AREAS = {
    "academicas": "Académicas", "investigacion": "Investigación", "culturales": "Culturales",
    "artisticas": "Artísticas", "deportivas": "Deportivas", "aprendizaje de idiomas": "Aprendizaje de idiomas",
    "responsabilidad social": "Responsabilidad social", "intercambio academico": "Intercambio académico",
    "innovacion y emprendimiento": "Innovación y emprendimiento", "institucional": "Institucional",
}


def _area(s: str) -> str:
    return _AREAS.get(texto.normalizar(s), s.capitalize() if s.isupper() else s)


def barra(hechas: int, total: int, ancho: int = 20) -> str:
    if total <= 0:
        return ""
    llenas = min(ancho, round(ancho * hechas / total))
    return pintar("█" * llenas, "oliva") + pintar("░" * (ancho - llenas), "tenue")


def _envolver(s: str, n: int = 4, ancho: int = 96) -> str:
    return "\n".join(textwrap.wrap(s, width=ancho, initial_indent=" " * n, subsequent_indent=" " * n))


# ---------------------------------------------------------------------- comandos


def cmd_perfil(nx, args, out) -> None:
    s = _siase(nx, args)
    p = s.perfil()
    ses = s.sesion()
    data = {"perfil": p.__dict__, "carrera": ses.carrera, "carreras": [c["nombre"] for c in ses.carreras]}

    def txt():
        print(pintar(texto.titulo(p.nombre), negrita=True))
        print(f"matrícula {p.matricula} · {texto.titulo(p.carrera)} · {p.plan}")
        if len(ses.carreras) > 1:
            print(pintar("otras carreras: " + "; ".join(c["nombre"] for c in ses.carreras[1:]), "tenue"))

    out.emitir(data, txt)


def _afis_filtradas(s: Siase, args) -> tuple[Any, list[Afi], set[int]]:
    mes = mes_desde(args.mes)
    lista = s.afis(mes)
    area = area_desde(args.area, lista.areas) if args.area else None
    if area:
        lista = s.afis(mes or lista.mes, area)
    ahora = texto.ahora()
    afis = lista.afis
    if not args.pasadas:
        afis = [a for a in afis if not a.fin or a.fin >= ahora]
    if args.con_cupo:
        afis = [a for a in afis if a.con_cupo]
    if args.buscar:
        q = texto.normalizar(args.buscar)
        afis = [a for a in afis if q in texto.normalizar(f"{a.evento} {a.descripcion} {a.organizador}")]
    if getattr(args, "semana", False):
        afis = [a for a in afis if a.inicio and 0 <= (a.inicio - ahora).total_seconds() <= 7 * 86400
                or (a.inicio and a.fin and a.inicio <= ahora <= a.fin)]
    afis.sort(key=lambda a: (a.inicio or datetime.max, a.id))
    mias = s.historial().ids()
    return lista, afis, mias


def cmd_afis(nx, args, out) -> None:
    s = _siase(nx, args)
    lista, afis, mias = _afis_filtradas(s, args)
    primera_vez = False
    if args.nuevas:
        visto = Visto(nx.c.state / "visto.db")
        primera_vez = not visto.hay_prefijo("siase:afi:")
        nuevas_ids = set() if primera_vez else {a.id for a in afis if visto.estado(f"siase:afi:{a.id}", "x")}
        visto.marcar([(f"siase:afi:{a.id}", "x") for a in lista.afis])
        visto.close()
        afis = [a for a in afis if a.id in nuevas_ids]
    mes_nombre = lista.meses.get(lista.mes or 0, str(lista.mes or ""))
    area_nombre = lista.areas.get(lista.area or 0, "todas") if lista.area else "todas"

    def txt():
        cupo = sum(a.con_cupo for a in afis)
        cab = f"{mes_nombre} · {len(afis)} AFIs"
        if not args.con_cupo:
            cab += f", {cupo} con cupo"
        cab += f" · área: {area_nombre.lower()}"
        if args.nuevas and primera_vez:
            print(f"Primera vez: registré las {len(lista.afis)} AFIs de {mes_nombre.lower()} como vistas. "
                  "Desde ahora `--nuevas` enseña solo las que aparezcan.")
            return
        if args.nuevas and not afis:
            print("No hay AFIs nuevas desde la última vez.")
            return
        print(pintar(cab, "tenue"))
        if not afis:
            print("Nada con esos filtros.")
            return
        filas = []
        for a in afis:
            evento = texto.recortar(a.evento, 58)
            if a.id in mias:
                evento = pintar("✓ ", "oliva") + evento
            filas.append([pintar(str(a.id), "tenue"), fmt_cupo(a), fmt_cuando(a),
                          pintar(texto.recortar(_area(a.area), 18), "hueso"), evento,
                          pintar(texto.recortar(texto.titulo(a.organizador), 30), "tenue")])
        _tabla(filas, ["ID", "CUPO", "CUÁNDO", "ÁREA", "EVENTO", "ORGANIZA"])
        if args.largo:
            for a in afis:
                print()
                print(pintar(f"{a.id}  {a.evento}", negrita=True))
                print(_envolver(a.descripcion or "(sin descripción)"))
        if mias & {a.id for a in afis}:
            print(pintar("\n✓ = ya estás pre-registrado", "tenue"))

    out.emitir({"mes": lista.mes, "area": lista.area, "areas": lista.areas, "meses": lista.meses,
                "afis": [a.as_dict() | {"mia": a.id in mias} for a in afis]}, txt)


def _buscar_afi(s: Siase, afi_id: int, mes: int | None) -> Afi | None:
    meses = [mes] if mes else [None]
    if not mes:
        hoy = texto.ahora()
        meses += [((hoy.month + k - 1) % 12) + 1 for k in (1, 2)]
    for m in meses:
        a = next((x for x in s.afis(m).afis if x.id == afi_id), None)
        if a:
            return a
    return None


def cmd_afi(nx, args, out) -> None:
    s = _siase(nx, args)
    hist = s.historial()
    ev = next((e for e in hist.eventos if e.id == args.id), None)
    afi = _buscar_afi(s, args.id, mes_desde(args.mes))
    if afi is None and ev is None:
        raise SiaseError(f"No encontré la AFI {args.id} este mes ni en los dos siguientes (prueba con --mes)")

    def txt():
        nombre = (afi.evento if afi else ev.evento)
        print(pintar(f"{args.id}  {nombre}", negrita=True))
        if afi:
            print(pintar(f"{_area(afi.area)} · {texto.titulo(afi.organizador)}", "tenue"))
            print(fmt_cuando(afi))
            reg = afi.registrados or 0
            print(f"Cupo: {fmt_cupo(afi)} ({reg} pre-registrado{'' if reg == 1 else 's'} de {afi.capacidad})")
        if ev:
            estado = "asististe" if ev.asistencia else ("ya pasó" if ev.fecha and ev.fecha < texto.ahora() else "pre-registrado")
            print(pintar(f"Tú: {estado}" + (f" · cuenta como oficial #{ev.num_oficial}" if ev.oficial else ""), "oliva"))
            for etiqueta, valor in (("Recinto", ev.recinto), ("Sede", ev.sede), ("Dirección", ev.direccion),
                                    ("Municipio", ev.municipio), ("Indicaciones", ev.indicaciones)):
                if valor:
                    print(_envolver(f"{etiqueta}: {valor}", 0))
        desc = (afi.descripcion if afi else "") or (ev.descripcion if ev else "")
        if desc:
            print()
            print(_envolver(desc, 0))
        if afi and not ev and afi.con_cupo:
            print(pintar(f"\nPara pre-registrarte: nexuscli siase inscribir {args.id}", "tenue"))

    out.emitir({"afi": afi.as_dict() if afi else None, "registro": ev.as_dict() if ev else None}, txt)


def cmd_historial(nx, args, out) -> None:
    s = _siase(nx, args)
    h = s.historial()
    eventos = sorted(h.eventos, key=lambda e: e.fecha or datetime.min, reverse=True)
    ahora = texto.ahora()

    def txt():
        faltan = max(h.requeridas - h.oficiales, 0)
        pct = f" {round(100 * h.oficiales / h.requeridas)} %" if h.requeridas else ""
        print(f"AFIs oficiales: {pintar(str(h.oficiales), negrita=True)} de {h.requeridas}  {barra(h.oficiales, h.requeridas)}{pct}")
        if faltan:
            print(pintar(f"te faltan {faltan}", "naranja"))
        print()
        filas = []
        for e in eventos:
            if e.fecha and e.fecha > ahora:
                asis = pintar("próxima", "naranja")
            else:
                asis = pintar("sí", "oliva") if e.asistencia else pintar("no", "rojo")
            of = pintar(f"#{e.num_oficial}", "oliva") if e.oficial else pintar("-", "tenue")
            filas.append([pintar(str(e.id), "tenue"), texto.fmt_fecha(e.fecha, anio=True), pintar(_area(e.area), "hueso"),
                          asis, of, texto.recortar(e.evento, 56), pintar(e.periodo, "tenue")])
        _tabla(filas, ["ID", "FECHA", "ÁREA", "ASISTENCIA", "OFICIAL", "EVENTO", "PERIODO"])

    out.emitir({"oficiales": h.oficiales, "requeridas": h.requeridas, "eventos": [e.as_dict() for e in eventos]}, txt)


def cmd_inscribir(nx, args, out) -> None:
    s = _siase(nx, args)
    mes = mes_desde(args.mes)
    afi = _buscar_afi(s, args.id, mes)
    if afi is None:
        raise SiaseError(f"No encontré la AFI {args.id} este mes ni en los dos siguientes (prueba con --mes)")
    if not out.json:
        print(pintar(f"{afi.id}  {afi.evento}", negrita=True))
        print(f"{_area(afi.area)} · {texto.titulo(afi.organizador)}")
        print(f"{fmt_cuando(afi)} · cupo {fmt_cupo(afi)}")
    _confirmar("¿Pre-registrarte en esta AFI?", args.si)
    r = s.preinscribir(args.id, afi.inicio.month if afi.inicio else mes)

    def txt():
        if r["registrada"]:
            print(pintar("Listo: ", "oliva", negrita=True) + "SIASE ya la muestra en tu historial.")
        else:
            print(pintar("Ojo: ", "naranja", negrita=True) + "SIASE no la muestra todavía en tu historial. Revísalo con "
                  "`nexuscli siase historial` o en la web.")
        for m in r["mensajes"]:
            print(pintar(f"SIASE dice: {m}", "tenue"))

    out.emitir(r, txt)


def cmd_liberar(nx, args, out) -> None:
    s = _siase(nx, args)
    ev: EventoAfi | None = next((e for e in s.historial().eventos if e.id == args.id), None)
    if ev is None:
        raise SiaseError(f"No estás pre-registrado en la AFI {args.id}")
    if not out.json:
        print(pintar(f"{ev.id}  {ev.evento}", negrita=True))
        print(f"{_area(ev.area)} · {texto.fmt_fecha(ev.fecha, anio=True)} · {ev.recinto}")
    _confirmar("¿Liberar tu lugar en esta AFI?", args.si)
    r = s.liberar(args.id)
    out.emitir(r, lambda: print(
        (pintar("Listo: ", "oliva", negrita=True) + "ya no está en tu historial.") if r["liberada"]
        else (pintar("Ojo: ", "naranja", negrita=True) + "SIASE todavía la muestra en tu historial.")))


def cmd_kardex(nx, args, out) -> None:
    k = _siase(nx, args).kardex()
    materias = k.materias
    if args.semestre:
        materias = [m for m in materias if m.semestre == str(args.semestre)]
    if args.pendientes:
        materias = [m for m in materias if not m.aprobada]

    def txt():
        aprobadas = sum(m.aprobada for m in k.materias)
        print(pintar(f"{texto.titulo(k.carrera)} · plan {k.plan}", "tenue"))
        prom = f" · promedio {k.promedio:g} (de las aprobadas)" if k.promedio else ""
        print(f"{aprobadas} de {len(k.materias)} materias aprobadas  {barra(aprobadas, len(k.materias))}{prom}")
        print()
        filas = []
        sem_prev = None
        for m in materias:
            if m.aprobada:
                final = pintar(f"{m.final} ✓", "oliva")
            elif m.cursada:
                final = pintar(m.final or "-", "rojo")
            else:
                final = pintar("-", "tenue")
            ops = [pintar(o, "rojo") if (o and not o.isdigit()) or (o.isdigit() and int(o) < 70) else o
                   for o in m.oportunidades]
            sem = m.semestre if m.semestre != sem_prev else ""
            sem_prev = m.semestre
            filas.append([pintar(sem, negrita=True), pintar(m.clave, "tenue"), texto.recortar(m.nombre, 44), *ops, final])
        _tabla(filas, ["SEM", "CLAVE", "MATERIA", "1ª", "2ª", "3ª", "4ª", "5ª", "6ª", "FINAL"])

    out.emitir({"carrera": k.carrera, "plan": k.plan, "promedio": k.promedio,
                "materias": [m.__dict__ | {"final": m.final, "aprobada": m.aprobada} for m in materias]}, txt)


def cmd_periodos(nx, args, out) -> None:
    ps = _siase(nx, args).periodos()
    out.emitir([p.__dict__ for p in ps], lambda: [print(f"{i}  {p.nombre}") for i, p in enumerate(ps, 1)])


def _color_cal(c: str) -> str:
    if c.isdigit():
        return pintar(c, "oliva" if int(c) >= 70 else "rojo")
    return pintar(c, "rojo") if c else pintar("-", "tenue")


def cmd_calificaciones(nx, args, out) -> None:
    periodo, cals = _siase(nx, args).calificaciones(args.periodo)

    def txt():
        print(pintar(periodo, negrita=True))
        if not cals:
            print("Sin materias en ese periodo.")
            return
        filas = [[pintar(c.clave, "tenue"), texto.recortar(c.materia, 46), c.tipo, c.grupo, c.fecha or pintar("-", "tenue"),
                  _color_cal(c.calificacion), c.oportunidad] for c in cals]
        _tabla(filas, ["CLAVE", "MATERIA", "TIPO", "GPO", "FECHA", "CAL", "OP"])
        if any(not c.calificacion for c in cals):
            print(pintar("\nSin calificación: todavía no la captura el profesor.", "tenue"))

    out.emitir({"periodo": periodo, "calificaciones": [c.__dict__ for c in cals]}, txt)


def cmd_horario(nx, args, out) -> None:
    h = _siase(nx, args).horario(args.periodo)
    colores = {m.abreviacion: _COLORES_MATERIA[i % len(_COLORES_MATERIA)] for i, m in enumerate(h.materias)}
    nombres = {m.abreviacion: m for m in h.materias}

    def txt():
        tot = h.totales
        extra = f" · {tot.get('Presenciales', '?')} h presenciales, {tot.get('Asíncronas', '0')} en línea" if tot else ""
        print(pintar(h.periodo, negrita=True) + pintar(extra, "tenue"))
        print()
        if args.lista:
            for b in h.bloques:
                m = nombres.get(b.abreviacion)
                print(f"{dia_nombre(b.dia):<10} {b.inicio}-{b.fin}  {pintar(b.abreviacion, colores.get(b.abreviacion), negrita=True):<6} "
                      f"{m.nombre if m else ''} · salón {b.salon} · grupo {b.grupo}")
        else:
            horas = sorted({b.inicio for b in h.bloques} | {b.fin for b in h.bloques})
            if horas:
                ini = int(horas[0][:2])
                fin = int(max(b.fin for b in h.bloques)[:2])
                dias = max((b.dia for b in h.bloques), default=4)
                dias = max(dias, 4)
                filas = []
                for hr in range(ini, fin):
                    fila = [pintar(f"{hr:02d}:00", "tenue")]
                    for d in range(dias + 1):
                        b = next((x for x in h.bloques if x.dia == d and x.inicio <= f"{hr:02d}:00" < x.fin), None)
                        fila.append(pintar(f"{b.abreviacion} {b.salon}", colores.get(b.abreviacion)) if b else pintar("·", "tenue"))
                    filas.append(fila)
                _tabla(filas, [""] + [dia_nombre(d) for d in range(dias + 1)])
        print()
        for m in h.materias:
            en_linea = "" if any(b.abreviacion == m.abreviacion for b in h.bloques) else pintar(" · sin horario presencial", "tenue")
            op = pintar(f" · {m.oportunidad}ª oportunidad", "naranja") if m.oportunidad not in ("1", "") else ""
            print(f"{pintar(f'{m.abreviacion:<6}', colores.get(m.abreviacion), negrita=True)} {m.nombre} "
                  + pintar(f"· grupo {m.grupo} · {m.oferta.lower()} · {m.creditos} créditos", "tenue") + op + en_linea)

    out.emitir({"periodo": h.periodo, "totales": h.totales, "materias": [m.__dict__ for m in h.materias],
                "bloques": [b.__dict__ | {"dia_nombre": dia_nombre(b.dia)} for b in h.bloques]}, txt)


# ---------------------------------------------------------------------- novedades


def novedades_siase(nx, visto: Visto) -> list[dict]:
    """Lo nuevo de SIASE para `nexuscli novedades --siase`. La primera vez solo registra."""
    s = Siase(nx.c)
    primera = not visto.hay_prefijo("siase:")
    regs: list[tuple[str, str, dict]] = []
    periodo, cals = s.calificaciones()
    for c in cals:
        if c.calificacion:
            regs.append((f"siase:cal:{periodo}:{c.clave}:{c.oportunidad}", huella(c.calificacion),
                         {"tipo": "calificación final", "curso": "SIASE", "tarea": f"{c.materia} ({c.oportunidad}ª)",
                          "texto": c.calificacion}))
    for e in s.historial().eventos:
        regs.append((f"siase:hist:{e.id}", huella(e.asistencia, e.oficial),
                     {"tipo": "afi", "curso": "SIASE", "tarea": e.evento,
                      "texto": ("asistencia registrada" + (f", oficial #{e.num_oficial}" if e.oficial else ""))
                      if e.asistencia else "pre-registro"}))
    from .siase_escolar import Escolar
    esc = Escolar(s)
    silenciosas: set[str] = set()
    antes = len(regs)
    try:
        ade = esc.adeudos()
        regs.append(("siase:adeudos", huella(ade.total, [c.__dict__ for c in ade.conceptos]),
                     {"tipo": "adeudo", "curso": "SIASE", "tarea": "otros adeudos",
                      "texto": f"total {_pesos(ade.total)}" + "".join(f"; {c.concepto}" for c in ade.conceptos)}))
        for enc in esc.encuestas():
            regs.append((f"siase:encuesta:{enc}", "x", {"tipo": "encuesta", "curso": "SIASE", "tarea": enc,
                                                         "texto": "encuesta pendiente en SIASE"}))
        for t in esc.tramites().tramites:
            regs.append((f"siase:tramite:{t.numero}", huella(t.estatus), {"tipo": "trámite", "curso": "SIASE",
                         "tarea": f"{t.documento} ({t.numero})", "texto": t.estatus}))
        periodo_ev, tablas_ev, _msg = esc.evaluaciones()
        for tb in tablas_ev:
            for fila in tb["filas"]:
                regs.append((f"siase:parcial:{periodo_ev}:{fila[0]}:{fila[1] if len(fila) > 1 else ''}", huella(fila),
                             {"tipo": "parcial", "curso": "SIASE", "tarea": " · ".join(fila[:2]),
                              "texto": " · ".join(f"{e}: {v}" for e, v in zip(tb["encabezados"], fila) if v)}))
        regs.append(("siase:escolar", "1", {}))
    except SiaseError:
        pass
    # Quien ya usaba `novedades --siase` antes de las consultas escolares: la primera lectura solo registra.
    if not visto.hay_prefijo("siase:escolar"):
        silenciosas.update(k for k, _, _ in regs[antes:])
    ahora = texto.ahora()
    for a in s.afis().afis:
        clave = f"siase:afi:{a.id}"
        regs.append((clave, "x", {"tipo": "afi nueva", "curso": "SIASE", "tarea": f"{a.id} {a.evento}",
                                  "texto": f"{fmt_cuando(a)} · {_area(a.area)} · cupo {a.disponibles}/{a.capacidad}"}))
        # Se marcan todas como vistas (así `siase afis --nuevas` coincide), pero solo se avisa de las que
        # todavía tienen cupo y no han terminado.
        if not a.con_cupo or (a.fin and a.fin < ahora):
            silenciosas.add(clave)
    hallazgos = []
    if not primera:
        for k, h, item in regs:
            estado = visto.estado(k, h)
            if estado and k not in silenciosas:
                hallazgos.append({"estado": estado, **item})
    visto.marcar([(k, h) for k, h, _ in regs])
    if primera:
        hallazgos.append({"estado": "nuevo", "tipo": "siase", "curso": "SIASE", "tarea": "SIASE",
                          "texto": f"Primera vez con SIASE: registré {len(regs)} cosas (calificaciones, parciales, adeudos, "
                                   "trámites, encuestas, historial y AFIs con cupo). Desde ahora solo verás lo nuevo."})
    return hallazgos


# ---------------------------------------------------------------------- consultas escolares


def _escolar(nx, args):
    from .siase_escolar import Escolar
    return Escolar(_siase(nx, args))


def _pesos(x: float | None) -> str:
    return "-" if x is None else f"${x:,.2f}"


def _fila_estado(etiqueta: str, valor: str) -> None:
    print(f"{pintar(f'{etiqueta:<16}', 'tenue')} {valor}")


def cmd_estado(nx, args, out) -> None:
    """Tablero con todo lo escolar de SIASE en una sola vista."""
    e = _escolar(nx, args)
    data: dict[str, Any] = {}
    errores: dict[str, str] = {}

    def intentar(clave: str, fn):
        try:
            data[clave] = fn()
        except SiaseError as ex:
            errores[clave] = str(ex)

    intentar("situacion", e.situacion)
    intentar("inscripcion", e.fecha_inscripcion)
    intentar("recibo", e.recibo)
    intentar("adeudos", e.adeudos)
    intentar("beca", e.beca)
    intentar("documentos", e.documentos)
    intentar("tramites", e.tramites)
    intentar("encuestas", e.encuestas)
    intentar("afis", e.s.historial)

    def txt():
        sit = data.get("situacion")
        if sit:
            foto = "foto aceptada" if sit.foto_aceptada else pintar("foto sin aceptar", "naranja")
            print(pintar(sit.semestre, negrita=True) + pintar(
                f" · {sit.tipo_inscripcion.lower()} · situación: {sit.situacion.lower()} · ", "tenue") + foto)
            print()
        ins = data.get("inscripcion")
        if ins:
            _fila_estado("inscripción", f"{ins.dia} a las {ins.hora}" + pintar(f" · {ins.periodo}", "tenue"))
        rec = data.get("recibo")
        if rec:
            if rec.pagado:
                cuando = f" el {rec.pago_fecha}" if rec.pago_fecha else ""
                _fila_estado("recibo", pintar("pagado", "oliva") + f" · {_pesos(rec.pago_monto or rec.total)}{cuando}")
            else:
                _fila_estado("recibo", pintar(f"por pagar {_pesos(rec.total)}", "naranja")
                             + (f" · antes del {rec.fecha_limite}" if rec.fecha_limite else ""))
        ade = data.get("adeudos")
        if ade:
            _fila_estado("adeudos", pintar("$0", "oliva") if not ade.total else pintar(_pesos(ade.total), "rojo")
                         + pintar(f" · {len(ade.conceptos)} conceptos (nexuscli siase adeudos)", "tenue"))
        beca = data.get("beca")
        if beca:
            _fila_estado("beca", beca.mensaje if beca.solicitud else pintar("sin solicitud", "tenue"))
        doc = data.get("documentos")
        if doc:
            color = "oliva" if "complet" in doc.estado.lower() else "naranja"
            _fila_estado("documentos", pintar(doc.estado.lower(), color)
                         + (pintar(f" · faltan {len(doc.pendientes)}", "naranja") if doc.pendientes else ""))
        tra = data.get("tramites")
        if tra is not None:
            if tra.tramites:
                _fila_estado("trámites DEyA", "; ".join(f"{t.documento.lower()}: {t.estatus.lower()}" for t in tra.tramites))
            else:
                _fila_estado("trámites DEyA", pintar("ninguno", "tenue"))
        enc = data.get("encuestas")
        if enc is not None:
            _fila_estado("encuestas", pintar(f"{len(enc)} pendiente{'s' if len(enc) != 1 else ''}", "naranja")
                         + f": {', '.join(enc)}" if enc else pintar("ninguna pendiente", "tenue"))
        h = data.get("afis")
        if h:
            _fila_estado("AFIs oficiales", f"{h.oficiales} de {h.requeridas}  {barra(h.oficiales, h.requeridas, 14)}")
        for clave, msg in errores.items():
            _fila_estado(clave, pintar(f"no se pudo leer: {msg}", "rojo"))

    def a_dict(x):
        if hasattr(x, "__dataclass_fields__"):
            from dataclasses import asdict
            return asdict(x)
        return x

    out.emitir({k: a_dict(v) for k, v in data.items()} | {"errores": errores}, txt)


def cmd_situacion(nx, args, out) -> None:
    sit = _escolar(nx, args).situacion()
    out.emitir(sit.__dict__, lambda: [
        _fila_estado("semestre", sit.semestre), _fila_estado("situación", sit.situacion.lower()),
        _fila_estado("inscripción", sit.tipo_inscripcion.lower()),
        _fila_estado("foto", "aceptada" if sit.foto_aceptada else "sin aceptar"), _fila_estado("división", sit.division)])


def cmd_inscripcion(nx, args, out) -> None:
    f = _escolar(nx, args).fecha_inscripcion()
    out.emitir(f.__dict__, lambda: print(f"{pintar(f.periodo, negrita=True)}\n{f.dia} a las {f.hora}"))


def cmd_adeudos(nx, args, out) -> None:
    a = _escolar(nx, args).adeudos()

    def txt():
        print(f"Adeudo total al {a.fecha}: " + (pintar("$0", "oliva") if not a.total else pintar(_pesos(a.total), "rojo")))
        if a.conceptos:
            print()
            _tabla([[c.cuenta, c.cantidad, c.concepto, _pesos(c.total)] for c in a.conceptos],
                   ["CUENTA", "CANTIDAD", "CONCEPTO", "TOTAL"])

    out.emitir({"fecha": a.fecha, "total": a.total, "conceptos": [c.__dict__ for c in a.conceptos]}, txt)


def cmd_recibo(nx, args, out) -> None:
    r = _escolar(nx, args).recibo(intersemestral=args.intersemestral)

    def txt():
        print(pintar(f"Recibo de servicios académicos · {r.periodo}", negrita=True))
        if r.inscripcion:
            print(pintar(r.inscripcion.lower(), "tenue"))
        print()
        filas = [[pintar(c.cuenta, "tenue"), c.concepto.capitalize(), f"{_pesos(c.importe):>10}"] for c in r.conceptos]
        filas.append(["", pintar("total", "tenue"), pintar(f"{_pesos(r.total):>10}", negrita=True)])
        _tabla(filas, ["CUENTA", "CONCEPTO", f"{'IMPORTE':>10}"])
        print()
        if r.pagado:
            extra = f" el {r.pago_fecha}" if r.pago_fecha else ""
            print(pintar("pagado", "oliva", negrita=True) + f"{extra} · {_pesos(r.pago_monto or r.total)}"
                  + (pintar(f" · transacción: {r.pago_estado.lower()}", "tenue") if r.pago_estado else ""))
        else:
            print(pintar("por pagar", "naranja", negrita=True) + (f" · antes del {r.fecha_limite}" if r.fecha_limite else ""))

    out.emitir(r.__dict__ | {"conceptos": [c.__dict__ for c in r.conceptos]}, txt)


def cmd_recibos(nx, args, out) -> None:
    rs = _escolar(nx, args).recibos_internos()
    out.emitir([r.__dict__ for r in rs], lambda: [
        print(f"{pintar(r.estado or '-', 'oliva' if 'pagad' in r.estado else 'naranja'):<10}  {r.nombre.capitalize()}")
        for r in rs] if rs else print("Sin recibos internos."))


def cmd_beca(nx, args, out) -> None:
    b = _escolar(nx, args).beca()
    out.emitir(b.__dict__, lambda: print(b.mensaje))


def cmd_encuestas(nx, args, out) -> None:
    enc = _escolar(nx, args).encuestas()
    out.emitir(enc, lambda: print("\n".join(f"· {x}" for x in enc) if enc else "No tienes encuestas pendientes."))


def cmd_tramites(nx, args, out) -> None:
    t = _escolar(nx, args).tramites()

    def txt():
        if t.tramites:
            _tabla([[x.numero, x.documento, x.fecha, x.importe, x.estatus] for x in t.tramites],
                   ["SOLICITUD", "DOCUMENTO", "FECHA", "IMPORTE", "ESTATUS"])
        else:
            print("No tienes trámites con el DEyA.")
        if t.se_pueden_pedir:
            print(pintar("\nSe pueden solicitar en la web: " + ", ".join(x.lower() for x in t.se_pueden_pedir), "tenue"))

    out.emitir({"tramites": [x.__dict__ for x in t.tramites], "se_pueden_pedir": t.se_pueden_pedir}, txt)


def cmd_documentos(nx, args, out) -> None:
    d = _escolar(nx, args).documentos()
    out.emitir(d.__dict__, lambda: (print(d.estado), [print(f"· {p}") for p in d.pendientes]))


def cmd_evaluaciones(nx, args, out) -> None:
    periodo, ts, msg = _escolar(nx, args).evaluaciones(args.periodo)

    def txt():
        print(pintar(periodo, negrita=True))
        if not ts:
            print(msg or "Sin evaluaciones parciales en este periodo.")
        for t in ts:
            print()
            _tabla(t["filas"], t["encabezados"])

    out.emitir({"periodo": periodo, "tablas": ts, "mensaje": msg}, txt)


def cmd_datos(nx, args, out) -> None:
    secciones = _escolar(nx, args).datos()
    if args.seccion:
        q = texto.normalizar(args.seccion)
        secciones = [s for s in secciones if q in texto.normalizar(s.titulo)]

    def txt():
        for s in secciones:
            print(pintar(s.titulo, "naranja", negrita=True))
            ancho = max(len(k) for k, _ in s.campos)
            for k, v in s.campos:
                print(f"  {pintar(f'{k:<{ancho}}', 'tenue')}  {v}")
            print()

    out.emitir([{"seccion": s.titulo, "campos": dict(s.campos)} for s in secciones], txt)

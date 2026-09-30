import json
from datetime import datetime

import pytest

from nexuscli.clonar import dueno
from nexuscli.cli import clasificar_novedades
from nexuscli.materias import CodigoError, Materias, avisos_de_cierre, proponer, registrar_clon, ultimo_clon
from nexuscli.nexus import Curso, NoEncontrado
from nexuscli.store import Visto


def test_propuestas_siguen_la_convencion_de_escuela():
    assert proponer("Análisis audiovisual | AGO26 | 101") == "anau"
    assert proponer("Creación narrativa y guionismo | AGO26 | 202") == "crng"
    assert proponer("Guion cinematográfico | AGO26 | 202") == "guci"
    assert proponer("Antropología visual | ENE26 | 102") == "anvi"
    assert proponer("Fotografía") == "foto"
    assert proponer("Análisis audiovisual", {"anau"}) == "anau2"


def test_archivo_de_materias(tmp_path):
    m = Materias(tmp_path / "materias")
    m.asignar(100001, "ANAU", "Análisis audiovisual | AGO26 | 101")
    with pytest.raises(CodigoError, match="ya es de"):
        m.asignar(100002, "anau", "Creación narrativa")
    with pytest.raises(CodigoError):
        m.asignar(100002, "con espacio", "x")
    with pytest.raises(CodigoError):
        m.asignar(100002, "123", "x")
    (tmp_path / "materias").write_text((tmp_path / "materias").read_text() + "\n# a mano\n100002 crng\n")
    m2 = Materias(tmp_path / "materias")
    assert m2.codigo(100001) == "anau" and m2.curso_id("CRNG") == 100002
    assert m2.nombres[100001] == "Análisis audiovisual | AGO26 | 101"
    assert m2.quitar(100002) and not m2.quitar(100002)


def test_menos_c_acepta_el_codigo(nx, fake):
    fake.on("Curso/ConsultarCarpetaCursos", {"Carpetas": [{"Cursos": [
        {"CursoId": 100001, "Nombre": "Análisis audiovisual | AGO26 | 101"},
        {"CursoId": 100002, "Nombre": "Guion cinematográfico | AGO26 | 202"}]}],
        "Paginacion": {"RegistrosPagina": 10, "RegistrosTotales": 2}})
    nx.materias.asignar(100002, "crng", "Guion cinematográfico | AGO26 | 202")
    nx.materias.asignar(100003, "anvi", "Antropología visual | ENE26 | 102")
    assert nx.curso("crng").id == 100002
    assert nx.curso("analisis").id == 100001
    with pytest.raises(NoEncontrado, match="ya no está activa"):
        nx.curso("anvi")


def _curso(cid, fin):
    return Curso(id=cid, nombre=f"Materia {cid} | AGO26 | 1", fin=fin)


def test_avisos_de_cierre(tmp_path):
    m = Materias(tmp_path / "materias")
    m.asignar(1, "anau", "Materia 1")
    ahora = datetime(2026, 12, 1, 12, 0)
    cursos = [_curso(1, "2026-12-18T23:59:00"), _curso(2, "2027-03-01T00:00:00"), _curso(3, "2026-11-30T23:59:00")]
    avisos = {a.curso_id: a for a in avisos_de_cierre(cursos, m, tmp_path, ahora)}
    assert set(avisos) == {1, 3}                        # la 2 termina en 3 meses
    assert avisos[1].motivo == "sin clon" and "nexuscli clonar -c anau" in avisos[1].comando
    assert avisos[3].motivo == "terminó" and "--como <código>" in avisos[3].comando

    clon = tmp_path / "docs" / "anau"
    clon.mkdir(parents=True)
    registrar_clon(tmp_path, 1, "Materia 1", clon)
    assert ultimo_clon(tmp_path, 1)["ruta"] == str(clon.resolve())

    def fechar(iso):
        datos = json.loads((tmp_path / "clones.json").read_text())
        datos["1"][0]["sincronizado"] = iso
        (tmp_path / "clones.json").write_text(json.dumps(datos))

    fechar("2026-11-28T10:00")                          # 3 días antes: al día, no avisa
    assert not avisos_de_cierre(cursos[:1], m, tmp_path, ahora)
    fechar("2026-11-01T10:00")                          # un mes: viejo
    (a,) = avisos_de_cierre(cursos[:1], m, tmp_path, ahora)
    assert a.motivo == "clon viejo" and a.comando == f"nexuscli clonar -c anau -o {clon.resolve().parent}"
    clon.rmdir()                                         # si la carpeta ya no existe, cuenta como sin clon
    assert avisos_de_cierre(cursos[:1], m, tmp_path, ahora)[0].motivo == "sin clon"


def test_clasificar_materia_nueva_no_inunda(tmp_path):
    v = Visto(tmp_path / "visto.db")
    a, b = _curso(1, None), _curso(2, None)
    regs_a = [("tarea:1:1:10", "h1", {"tipo": "tarea", "curso": "a", "cierre": "2999-01-01T00:00:00"})]
    regs_b = [("tarea:2:1:20", "h2", {"tipo": "tarea", "curso": "b", "cierre": "2999-02-01T00:00:00"}),
              ("retro:5", "h3", {"tipo": "comentario", "curso": "b"})]

    r = clasificar_novedades(v, [(a, regs_a)])
    assert r["primera"] and r["hallazgos"] == []
    v.marcar(r["marcas"]); v.conocer(r["materias"])

    r = clasificar_novedades(v, [(a, regs_a), (b, regs_b)])
    assert [h["tipo"] for h in r["hallazgos"]] == ["materia nueva"]
    assert "1 tareas" in r["hallazgos"][0]["texto"]
    v.marcar(r["marcas"]); v.conocer(r["materias"])

    regs_b.append(("retro:6", "h4", {"tipo": "comentario", "curso": "b"}))
    r = clasificar_novedades(v, [(a, regs_a), (b, regs_b)])
    assert [(h["tipo"], h["estado"]) for h in r["hallazgos"]] == [("comentario", "nuevo")]


def test_base_vieja_sin_tabla_de_materias(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "visto.db")
    db.execute("CREATE TABLE visto (clave TEXT PRIMARY KEY, huella TEXT NOT NULL, visto_en TEXT NOT NULL)")
    db.execute("INSERT INTO visto VALUES ('tarea:100001:1:5', 'x', 'hoy')")
    db.commit(); db.close()
    v = Visto(tmp_path / "visto.db")
    assert v.materia_conocida(100001) and not v.materia_conocida(100002)


def test_dueno_de_carpeta(tmp_path):
    assert dueno(tmp_path) is None
    (tmp_path / ".nexuscli.json").write_text('{"curso_id": 100001, "curso": "Análisis"}')
    assert dueno(tmp_path) == (100001, "Análisis")


def test_todo_se_guarda_privado(tmp_path):
    import stat

    def modo(p):
        return oct(stat.S_IMODE(p.stat().st_mode))

    m = Materias(tmp_path / "conf" / "materias")
    m.asignar(1, "anau", "Materia 1")
    registrar_clon(tmp_path / "estado", 1, "Materia 1", tmp_path)
    Visto(tmp_path / "estado" / "visto.db").close()
    assert modo(tmp_path / "conf") == "0o700" and modo(tmp_path / "conf" / "materias") == "0o600"
    assert modo(tmp_path / "estado") == "0o700"
    assert modo(tmp_path / "estado" / "clones.json") == "0o600"
    assert modo(tmp_path / "estado" / "visto.db") == "0o600"

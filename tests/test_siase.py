import stat
import time

import httpx
import pytest

from nexuscli import config
from nexuscli import siase as S
from nexuscli.client import Client
from nexuscli.pace import Pacer
from tests import siase_falso as F


@pytest.fixture
def falso():
    return F.SiaseFalso()


@pytest.fixture
def sia(falso, tmp_path):
    c = Client(pacer=Pacer("off"), state=tmp_path, http=httpx.Client(transport=httpx.MockTransport(falso)),
               credenciales=config.Credenciales(F.MATRICULA, "secreta", "test"))
    return S.Siase(c)


def paginas(falso, nombre):
    return [r for r in falso.peticiones if r.url.path.endswith(nombre)]


# ---------------------------------------------------------------------- parsers


def test_login_saca_trim_y_carrera():
    trim, carreras = S.parse_login(F.pagina_login())
    assert trim == F.TRIM
    assert len(carreras) == 1
    assert carreras[0].claves == F.CLAVES
    assert carreras[0].usuario == F.MATRICULA
    assert "LENG. Y PROD. AUDIOVISUAL" in carreras[0].nombre


def test_login_rechazado():
    with pytest.raises(S.SiaseError, match="incorrect"):
        S.parse_login(F.pagina_error("Usuario o contraseña incorrectos."))


def test_afis():
    lista = S.parse_afis(F.pagina_afis(F.AFIS, 10))
    assert lista.mes == 10 and lista.area == 0
    assert lista.areas[5] == "Deportivas" and lista.meses[10] == "Octubre"
    por_id = {a.id: a for a in lista.afis}
    llena = por_id[4101]
    assert llena.lleno and not llena.con_cupo and llena.disponibles == 0
    danza = por_id[4102]
    assert (danza.capacidad, danza.registrados, danza.disponibles) == (500, 118, 382)
    assert danza.con_cupo and danza.descripcion.startswith("Presentación de los grupos")
    assert danza.inicio.isoformat() == "2026-10-09T11:00:00"


def test_alertas_ignora_las_de_funciones():
    pagina = F.pagina_afis(F.AFIS, 10)
    assert "No ha seleccionado un evento..." in pagina
    assert S.alertas(pagina) == []
    assert S.alertas(F.pagina_error("Procedimiento restringido, iniciar sesion nuevamente.")) == [
        "Procedimiento restringido, iniciar sesion nuevamente."]
    with pytest.raises(S.SesionVencida):
        S.revisar_sesion(F.pagina_error("El tiempo de inactividad (30 minutos) excedio, iniciar sesion nuevamente."))


def test_historial():
    h = S.parse_historial(F.pagina_historial(F.HISTORIAL, 4))
    assert (h.oficiales, h.requeridas, len(h.eventos)) == (4, 14, 5)
    e = next(x for x in h.eventos if x.id == 5201)
    assert e.evento.startswith("Obra de teatro") and e.asistencia and e.oficial and e.num_oficial == 2
    assert e.recinto == "Aula Magna del Colegio Civil" and e.sede == "Colegio Civil"
    assert e.municipio == "MONTERREY" and e.organizador == "DIRECCION DE DESARROLLO CULTURAL"
    assert e.periodo == "Agosto-Diciembre 2025" and e.fecha.year == 2025


def test_kardex():
    k = S.parse_kardex(F.pagina_kardex())
    assert k.plan == "430" and "LENG. Y PROD" in k.carrera
    paz = k.materias[0]
    assert paz.oportunidades[:3] == ["58", "NC", "82"] and paz.final == "82" and paz.aprobada and paz.intentos == 3
    guion = next(m for m in k.materias if m.clave == "301")
    assert not guion.aprobada and guion.cursada
    assert not next(m for m in k.materias if m.clave == "401").cursada
    assert k.promedio == round((82 + 93 + 81 + 90 + 87 + 79) / 6, 2)


def test_calificaciones_y_periodos():
    form = S.parse_periodos(F.pagina_periodos("econcfs02"))
    assert form.campo == "HTMLPeriodo" and form.resill == "40002" and form.accion.endswith("HTMLTipCve=01")
    assert [p.nombre for p in form.periodos] == ["Semestral Agosto-Diciembre 2026", "Semestral Enero - Junio 2026"]
    assert S.elegir_periodo(form.periodos, "ene jun 2026").valor == "0x00000000003b9101"
    assert S.elegir_periodo(form.periodos, "2").valor == "0x00000000003b9101"
    assert S.elegir_periodo(form.periodos, None).valor == "0x00000000003b9471"
    periodo, cal = S.parse_calificaciones(F.pagina_calificaciones("0x00000000003b9101"))
    assert periodo == "Enero - Junio 2026"
    assert [(c.materia, c.calificacion, c.oportunidad) for c in cal][-1] == ("Guion cinematográfico", "64", "1")
    _, actual = S.parse_calificaciones(F.pagina_calificaciones("0x00000000003b9471"))
    assert actual[0].fecha == "" and actual[0].calificacion == ""


def test_horario_une_horas_seguidas():
    h = S.parse_horario(F.pagina_horario(), "Agosto-Diciembre 2026")
    assert [m.abreviacion for m in h.materias] == ["GUCI", "SEIM", "ILFO", "MONT"]
    bloques = {(b.dia, b.abreviacion): (b.inicio, b.fin, b.salon) for b in h.bloques}
    assert bloques[(0, "SEIM")] == ("08:00", "10:00", "A105")
    assert bloques[(1, "ILFO")] == ("12:00", "15:00", "SET2")
    assert bloques[(2, "GUCI")] == ("16:00", "18:00", "C104")
    assert h.totales == {"Presenciales": "9", "Asíncronas": "3", "Totales": "12"}


def test_perfil():
    p = S.parse_perfil(F.pagina_perfil())
    assert (p.matricula, p.nombre, p.plan) == (F.MATRICULA, "ANA LOPEZ GARZA", "Modelo Academico 2020")
    assert p.carrera.startswith("LIC. EN LENG.")


def test_meses_y_areas():
    assert S.mes_desde("octubre") == 10 and S.mes_desde("oct") == 10 and S.mes_desde("3") == 3
    areas = S.parse_afis(F.pagina_afis(F.AFIS, 10)).areas
    assert S.area_desde("deportivas", areas) == 5 and S.area_desde("cultural", areas) == 3


# ---------------------------------------------------------------------- cliente


def test_sesion_se_guarda_privada_y_se_reusa(sia, falso, tmp_path):
    sia.afis(10)
    sia.historial()
    assert len(paginas(falso, "eselcarrera.htm")) == 1
    assert stat.S_IMODE((tmp_path / "siase.json").stat().st_mode) == 0o600
    otra = S.Siase(sia.c)
    otra.kardex()
    assert len(paginas(falso, "eselcarrera.htm")) == 1  # la sesión guardada sigue vigente
    datos = __import__("json").loads((tmp_path / "siase.json").read_text())
    datos["ultimo_uso"] = time.time() - S.INACTIVIDAD - 5
    (tmp_path / "siase.json").write_text(__import__("json").dumps(datos))
    S.Siase(sia.c).kardex()
    assert len(paginas(falso, "eselcarrera.htm")) == 2  # vencida por inactividad: login nuevo


def test_sesion_vencida_reintenta(sia, falso):
    sia.afis(10)
    falso.vencer_una_vez = True
    assert S.parse_kardex  # noqa
    k = sia.kardex()
    assert k.materias and len(paginas(falso, "eselcarrera.htm")) == 2


def test_consultas_mandan_las_claves(sia, falso):
    sia.afis(10, area=3)
    r = paginas(falso, "delSavePrereg.htm")[-1]
    q = dict(r.url.params)
    assert q["HTMLtrim"] == F.TRIM and q["HTMLUsuario"] == F.MATRICULA and q["HTMLCveMes"] == "10"
    assert q["HTMLCveArea"] == "3" and all(q[k] == v for k, v in F.CLAVES.items())


def test_calificaciones_por_control_p(sia, falso):
    periodo, cal = sia.calificaciones("ene jun")
    assert periodo == "Semestral Enero - Junio 2026" and len(cal) == 3
    post = paginas(falso, "control.p")[-1]
    cuerpo = dict(x.split("=", 1) for x in post.content.decode().split("&"))
    assert cuerpo == {"HTMLPeriodo": "0x00000000003b9101", "HTMLTrund": "econcfs02", "HTMLResill": "40002"}


def test_horario_guarda_abreviaturas(sia):
    sia.horario()
    assert S.abreviatura_oficial(sia.c.state, "Guion cinematográfico | AGO26 | 202") == "guci"
    assert S.abreviatura_oficial(sia.c.state, "Semiótica de la imagen | AGO26 | 201") == "seim"
    assert S.abreviatura_oficial(sia.c.state, "Materia que no existe") is None


# ---------------------------------------------------------------------- escribir


def test_preinscribir_sigue_los_pasos_de_la_web(sia, falso):
    r = sia.preinscribir(4102, 10)
    assert r["registrada"] and r["mensajes"] == ["Pre registro guardado."]
    sel = [p for p in paginas(falso, "delSavePrereg.htm") if p.method == "POST"]
    assert len(sel) == 1 and dict(sel[0].url.params)["HTMLCveEvento"] == "4102"
    assert "Evento%5B%5D=4102" in sel[0].content.decode()
    (guardar,) = paginas(falso, "delSavePreReg20")
    q = dict(guardar.url.params)
    assert q["HTMLCveEvento"] == "4102" and q["HTMLSaveDelReg"] == "0" and q["HTMLtrim"] == F.TRIM


def test_preinscribir_no_toca_llenas_ni_las_tuyas(sia, falso):
    with pytest.raises(S.SiaseError, match="cupo"):
        sia.preinscribir(4101, 10)
    falso.historial.append(F.EventoFalso(4103, "Masterclass", "ACADEMICAS", "12/10/2026 10:00", False, False, 0, "x"))
    with pytest.raises(S.SiaseError, match="Ya estás"):
        sia.preinscribir(4103, 10)
    assert not paginas(falso, "delSavePreReg20")  # nunca mandó la petición que alterna


def test_liberar(sia, falso):
    with pytest.raises(S.SiaseError, match="No estás"):
        sia.liberar(4102)
    sia.preinscribir(4102, 10)
    r = sia.liberar(4102)
    assert r["liberada"] and 4102 not in sia.historial().ids()
    with pytest.raises(S.SiaseError, match="asistencia"):
        sia.liberar(5201)


# ---------------------------------------------------------------------- CLI


def test_cli_siase(monkeypatch, falso, tmp_path, capsys):
    from nexuscli import cli, texto
    from datetime import datetime

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "conf"))
    monkeypatch.setattr(texto, "ahora", lambda: datetime(2026, 10, 8, 10, 30))

    def cliente(pacer=None, verbose=False):
        return Client(pacer=Pacer("off"), state=tmp_path, http=httpx.Client(transport=httpx.MockTransport(falso)),
                      credenciales=config.Credenciales(F.MATRICULA, "x", "test"))

    monkeypatch.setattr(cli, "Client", cliente)
    cli.main(["siase", "afis", "-m", "10", "-d"])
    salida = capsys.readouterr().out
    assert "Octubre" in salida and "Muestra de danza folklórica UANL" in salida and "382/500" in salida
    assert "Ciclo de cine" not in salida  # llena
    cli.main(["siase", "historial"])
    salida = capsys.readouterr().out
    assert "AFIs oficiales: 4 de 14" in salida and "te faltan 10" in salida
    cli.main(["siase", "horario"])
    salida = capsys.readouterr().out
    assert "SEIM A105" in salida and "MONT" in salida and "sin horario presencial" in salida
    with pytest.raises(SystemExit):
        cli.main(["siase", "inscribir", "4102"])  # sin terminal ni -y: no inscribe
    assert not paginas(falso, "delSavePreReg20")

from datetime import datetime

from nexuscli import texto
from nexuscli.pace import PERFILES, Pacer


class Reloj:
    def __init__(self):
        self.t = 0.0
        self.dormido: list[float] = []

    def sleep(self, d):
        self.dormido.append(d)
        self.t += d

    def clock(self):
        return self.t


def test_pace_off_no_duerme():
    r = Reloj()
    p = Pacer("off", sleep=r.sleep, clock=r.clock)
    for _ in range(5):
        p.antes()
        p.despues()
    assert r.dormido == []


def test_pace_normal_es_aleatorio_y_acotado():
    r = Reloj()
    p = Pacer("normal", sleep=r.sleep, clock=r.clock)
    for _ in range(200):
        p.antes()
        p.despues()
    assert r.dormido[0] <= 0.6                      # primera petición: respiro corto
    resto = r.dormido[1:]
    assert len(set(round(d, 6) for d in resto)) == len(resto)  # nunca dos iguales
    assert all(0 < d <= PERFILES["normal"].tope for d in resto)
    mediana = sorted(resto)[len(resto) // 2]
    assert 0.6 < mediana < 2.5


def test_pace_descuenta_el_tiempo_ya_pasado():
    r = Reloj()
    p = Pacer("normal", sleep=r.sleep, clock=r.clock)
    p.antes()
    p.despues()
    r.t += 60  # el usuario tardó un minuto en el siguiente comando
    assert p.antes() == 0.0


def test_html_a_texto():
    html = '<p>1.&nbsp;Ingresa a <strong>Recursos</strong></p><p>2. Lee <a href="http://x.mx/a">esto</a></p><ul><li>uno</li><li>dos</li></ul>'
    assert texto.html_a_texto(html) == "1. Ingresa a Recursos\n2. Lee esto (http://x.mx/a)\n• uno\n• dos"


def test_fechas_y_nombres():
    assert texto.fecha("0001-01-01T00:00:00") is None
    assert texto.fecha("2026-10-12T23:59:00") == datetime(2026, 10, 12, 23, 59)
    assert texto.relativo(datetime(2026, 10, 12), datetime(2026, 10, 9)) == "en 3 d"
    assert texto.relativo(datetime(2026, 10, 9, 10), datetime(2026, 10, 9, 12)) == "hace 2 h"
    assert texto.curso_corto("Análisis audiovisual | AGO26 | 101") == "Análisis audiovisual"
    assert texto.normalizar("  Creación  NARRATIVA ") == "creacion narrativa"

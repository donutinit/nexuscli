"""Regenera las capturas del README: `uv run python docs/capturas/generar.py`.

Corre el CLI de verdad contra el Nexus de mentira de demo.py, con la hora fija, guarda la
salida con color y la dibuja en una ventana de terminal (IBM Plex Mono, paleta de cuarto
oscuro) que Chromium en modo headless convierte a PNG. Necesita Chromium o Chrome: usa
$CHROME, o el de Playwright en ~/.cache/ms-playwright, o `chromium` del PATH.
"""

from __future__ import annotations

import contextlib
import html
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).parent))

from demo import DemoNexus  # noqa: E402
from tests.siase_falso import EventoFalso, SiaseFalso  # noqa: E402
from nexuscli import cli, config, texto  # noqa: E402
from nexuscli.client import Client, Sesion  # noqa: E402
from nexuscli.pace import Pacer  # noqa: E402

IMG = RAIZ / "docs" / "img"
AHORA = datetime(2026, 10, 8, 10, 30)
FUENTE = "IBM Plex Mono"
COLS_MIN = 72


# ---------------------------------------------------------------------- correr el CLI


class Sesiones:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.demo = DemoNexus()
        self.siase = SiaseFalso()
        # Un pre-registro a futuro, para que el historial tenga una "próxima".
        self.siase.historial.append(EventoFalso(4106, "UANL IT Summit: bloque de diseño", "INNOVACION Y EMPRENDIMIENTO",
                                                "20/10/2026 10:00", False, False, 0, "Agosto-Diciembre 2026"))
        (tmp / "config" / "nexuscli").mkdir(parents=True)
        (tmp / "config" / "nexuscli" / "materias").write_text("100001 seim\n100002 guci\n")
        os.environ.update({"XDG_CONFIG_HOME": str(tmp / "config"), "NEXUS_STATE_DIR": str(tmp / "estado"),
                           "FORCE_COLOR": "1", "NEXUS_PACE": "off", "COLUMNS": "200"})
        os.environ.pop("NO_COLOR", None)
        texto.ahora = lambda: AHORA  # todo el CLI pregunta la hora por aquí
        cli.confirmar = lambda pregunta, si: print(f"{pregunta} [s/N] s")
        demo, siase = self.demo, self.siase

        def transporte(req: httpx.Request) -> httpx.Response:
            return siase(req) if req.url.host == "deimos.dgi.uanl.mx" else demo(req)

        def cliente(pacer=None, verbose=False):
            c = Client(pacer=Pacer("off"), state=tmp / "estado",
                       http=httpx.Client(transport=httpx.MockTransport(transporte)),
                       credenciales=config.Credenciales("1234567", "demo", "demo"))
            c._sesion = Sesion(token="demo", area_id=1, rol_id=5, cuenta_id=100200, expira=time.time() + 3600)
            return c

        cli.Client = cliente

    def correr(self, *argv: str) -> str:
        buf = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                try:
                    cli.main(list(argv))
                except SystemExit:
                    pass
        finally:
            os.chdir(cwd)
        return buf.getvalue().rstrip("\n")


# ---------------------------------------------------------------------- ANSI a HTML


_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def ansi_a_html(texto_ansi: str) -> str:
    out: list[str] = []
    abierto = False
    pos = 0
    for m in _SGR.finditer(texto_ansi):
        out.append(html.escape(texto_ansi[pos:m.start()]))
        pos = m.end()
        if abierto:
            out.append("</span>")
            abierto = False
        codigos = [c for c in m.group(1).split(";") if c]
        estilos = []
        i = 0
        while i < len(codigos):
            c = codigos[i]
            if c == "1":
                estilos.append("font-weight:600")
            elif c == "2":
                estilos.append("opacity:.6")
            elif c == "38" and i + 4 < len(codigos) + 1 and codigos[i + 1] == "2":
                r, g, b = codigos[i + 2:i + 5]
                estilos.append(f"color:rgb({r},{g},{b})")
                i += 4
            i += 1
        if estilos:
            out.append(f'<span style="{";".join(estilos)}">')
            abierto = True
    out.append(html.escape(texto_ansi[pos:]))
    if abierto:
        out.append("</span>")
    return "".join(out)


def ancho_visible(linea: str) -> int:
    return len(_SGR.sub("", linea))


# ---------------------------------------------------------------------- dibujo

GRANO = ("data:image/svg+xml;utf8," + html.escape(
    "<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='g'>"
    "<feTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' seed='7' stitchTiles='stitch'/>"
    "<feColorMatrix type='saturate' values='0'/><feComponentTransfer><feFuncA type='table' tableValues='0 .07'/>"
    "</feComponentTransfer></filter><rect width='100%' height='100%' filter='url(%23g)'/></svg>"))

CSS_BASE = f"""
@font-face {{ font-family: marcas; src: local("Adwaita Mono"); unicode-range: U+2713, U+2717; }}
html, body {{ margin: 0; background: transparent; }}
body {{ padding: 36px 44px 60px; font-family: marcas, "{FUENTE}", monospace; }}
.win {{ display: inline-block; position: relative; border-radius: 12px; overflow: hidden;
  background: #1b1a1e; box-shadow: 0 28px 64px rgba(0,0,0,.42), 0 0 0 1px rgba(216,207,192,.08); }}
.win::after {{ content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image: url("{GRANO}"); }}
.bar {{ height: 38px; display: flex; align-items: center; gap: 8px; padding: 0 16px;
  background: #17161a; border-bottom: 1px solid rgba(216,207,192,.06); }}
.dot {{ width: 11px; height: 11px; border-radius: 50%; opacity: .85; }}
.titulo {{ flex: 1; text-align: center; font-size: 12.5px; color: #7d766c; letter-spacing: .02em;
  margin-right: 60px; }}
pre {{ margin: 0; padding: 22px 30px 26px; font: 15px/1.6 marcas, "{FUENTE}", monospace; color: #d8cfc0;
  white-space: pre; }}
.prompt {{ color: #d9873f; }}
.cmd {{ color: #efe7da; font-weight: 600; }}
"""


def titulo_ventana(comando: str) -> str:
    """'nexuscli siase afis -m octubre' -> 'nexuscli · siase afis'."""
    palabras = comando.split()[1:]
    sub = []
    for p in palabras:
        if p.startswith("-"):
            break
        sub.append(p)
    n = 2 if sub[:1] == ["siase"] else 1
    return " · ".join(["nexuscli", " ".join(sub[:n])])


def ventana(comando: str, salida: str) -> tuple[str, int, int]:
    lineas = salida.splitlines()
    cols = max([COLS_MIN, len(comando) + 2] + [ancho_visible(l) for l in lineas])
    cuerpo = f'<span class="prompt">$</span> <span class="cmd">{html.escape(comando)}</span>\n' + ansi_a_html(salida)
    doc = f"""<!doctype html><meta charset="utf-8"><style>{CSS_BASE}</style>
<div class="win"><div class="bar">
<span class="dot" style="background:#b23a2f"></span><span class="dot" style="background:#d9873f"></span>
<span class="dot" style="background:#5c6b52"></span><div class="titulo">{html.escape(titulo_ventana(comando))}</div>
</div><pre style="min-width:{round(cols * 9.0)}px">{cuerpo}</pre></div>"""
    ancho = 44 * 2 + 30 * 2 + round(cols * 9.0) + 4
    alto = 36 + 60 + 38 + 22 + 26 + round((len(lineas) + 1) * 24) + 2
    return doc, ancho, alto


def chromium() -> str:
    candidatos = [os.environ.get("CHROME", "")]
    candidatos += sorted(str(p) for p in Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux*/chrome"))
    candidatos += [shutil.which(n) or "" for n in ("chromium", "chromium-browser", "google-chrome")]
    for c in candidatos:
        if c and Path(c).exists():
            return c
    raise SystemExit("No encontré Chromium: define CHROME=/ruta/a/chrome")


def png(doc: str, ancho: int, alto: int, destino: Path, escala: float = 2) -> None:
    with tempfile.TemporaryDirectory() as d:
        pagina = Path(d) / "p.html"
        pagina.write_text(doc, encoding="utf-8")
        subprocess.run([
            chromium(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
            f"--force-device-scale-factor={escala}", f"--window-size={ancho},{alto}",
            "--default-background-color=00000000", f"--screenshot={destino}", pagina.as_uri(),
        ], check=True, capture_output=True, timeout=60)
    print(f"  {destino.relative_to(RAIZ)}  ({destino.stat().st_size // 1024} KB)")


def captura(nombre: str, comando: str, salida: str) -> None:
    doc, ancho, alto = ventana(comando, salida)
    png(doc, ancho, alto, IMG / f"{nombre}.png")


# ---------------------------------------------------------------------- banner

GRANO_FUERTE = ("data:image/svg+xml;utf8," + html.escape(
    "<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'><filter id='g'>"
    "<feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' seed='29' stitchTiles='stitch'/>"
    "<feColorMatrix type='saturate' values='0'/><feComponentTransfer><feFuncA type='table' tableValues='0 .16'/>"
    "</feComponentTransfer></filter><rect width='100%' height='100%' filter='url(%23g)'/></svg>"))


def recorte(salida: str, desde: int, hasta: int) -> str:
    return "\n".join(salida.splitlines()[desde:hasta])


def banner(cuadros: list[tuple[str, str]]) -> None:
    """Hoja de contacto: cuatro cuadros de 6x6; el primero es el título."""
    marcas = ["▸ 12", "▸ 12A  NEXUSCLI 400", "▸ 13", "▸ 13A  NEXUSCLI 400"]
    etiquetas = ["01", "02 tareas", "03 afis con cupo", "04 novedades"]
    celdas = [f"""<div class="cuadro titulo"><div>
      <div class="marca">nexuscli<span class="cursor"></span></div>
      <div class="lema">nexus y siase desde la terminal</div>
      <div class="sub">tareas · entregas en equipo · comentarios<br>afis con cupo · kardex · horario</div>
    </div></div>"""]
    for comando, salida in cuadros:
        celdas.append(f"""<div class="cuadro"><pre><span class="prompt">$</span> <b>{html.escape(comando)}</b>
{ansi_a_html(salida)}</pre></div>""")
    arriba = "".join(f"<span>{m}</span>" for m in marcas)
    abajo = "".join(f"<span>{e}</span>" for e in etiquetas)
    perf = "<i></i>" * 38
    doc = f"""<!doctype html><meta charset="utf-8"><style>
@font-face {{ font-family: marcas; src: local("Adwaita Mono"); unicode-range: U+2713, U+2717; }}
html, body {{ margin: 0; background: #131215; }}
.hoja {{ position: relative; width: 1600px; height: 440px; overflow: hidden; font-family: "{FUENTE}", monospace;
  background: linear-gradient(180deg, #1c1a1e 0%, #141317 16%, #131215 84%, #1b191d 100%); }}
.hoja::after {{ content: ""; position: absolute; inset: 0; pointer-events: none; background-image: url("{GRANO_FUERTE}"); }}
.perf {{ position: absolute; left: 0; right: 0; height: 15px; display: flex; gap: 20px; padding-left: 10px; }}
.perf.arriba {{ top: 11px; }} .perf.abajo {{ bottom: 11px; }}
.perf i {{ flex: none; width: 22px; height: 15px; border-radius: 3px; background: #09080a;
  box-shadow: inset 0 1px 0 rgba(255,243,221,.08), 0 0 0 1px rgba(0,0,0,.4); }}
.fila {{ position: absolute; left: 40px; right: 40px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 22px; }}
.bordes {{ top: 34px; font-size: 10.5px; letter-spacing: .16em; color: #d9873f; opacity: .72; }}
.etiquetas {{ bottom: 36px; font-size: 10.5px; letter-spacing: .16em; color: #7d766c; }}
.cuadros {{ top: 56px; height: 320px; }}
.cuadro {{ position: relative; overflow: hidden; border-radius: 3px; background: #1b1a1e;
  box-shadow: 0 0 0 1px rgba(216,207,192,.09), inset 0 0 60px rgba(0,0,0,.55); }}
.cuadro pre {{ margin: 0; padding: 18px 18px; font: 11.5px/1.66 marcas, "{FUENTE}", monospace; color: #d8cfc0;
  white-space: pre; }}
.cuadro pre b {{ color: #efe7da; font-weight: 600; }}
.prompt {{ color: #d9873f; }}
.titulo {{ display: grid; place-items: center; background: radial-gradient(120% 90% at 30% 20%, #242127 0%, #1a191d 70%); }}
.marca {{ font-size: 44px; font-weight: 600; color: #efe7da; letter-spacing: -.01em; }}
.cursor {{ display: inline-block; width: 13px; height: 36px; margin-left: 8px; vertical-align: -5px; background: #d9873f; opacity: .9; }}
.lema {{ margin-top: 14px; font: 300 17px "IBM Plex Sans", sans-serif; color: #d8cfc0; letter-spacing: .01em; }}
.sub {{ margin-top: 18px; font-size: 11px; line-height: 1.7; color: #7d766c; }}
</style>
<div class="hoja">
  <div class="perf arriba">{perf}</div>
  <div class="fila bordes">{arriba}</div>
  <div class="fila cuadros">{"".join(celdas)}</div>
  <div class="fila etiquetas">{abajo}</div>
  <div class="perf abajo">{perf}</div>
</div>"""
    png(doc, 1600, 440, IMG / "banner.png", escala=1.5)


# ---------------------------------------------------------------------- guion


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = Sesiones(tmp)

        tareas = s.correr("tareas")
        captura("tareas", "nexuscli tareas", tareas)
        s.correr("novedades")                      # primera vez: registra todo en silencio
        s.demo.cambios_de_la_semana()
        novedades = s.correr("novedades")
        captura("novedades", "nexuscli novedades", novedades)
        captura("tarea", "nexuscli tarea 2.2 -c seim", s.correr("tarea", "2.2", "-c", "seim"))

        pdf = tmp / "EQUIPO3_ACT2.2_storyboard.pdf"
        with pdf.open("wb") as fh:
            fh.truncate(2_431_000)
        captura("entregar", "nexuscli entregar 2.2 EQUIPO3_ACT2.2_storyboard.pdf -c seim",
                s.correr("entregar", "2.2", str(pdf), "-c", "seim"))
        clonar = s.correr("clonar", "-c", "seim", "-o", "escuela")
        captura("clonar", "nexuscli clonar -c seim -o escuela", clonar)
        captura("cursos", "nexuscli cursos", s.correr("cursos"))

        afis = s.correr("siase", "afis", "-m", "octubre", "-d")
        captura("siase-afis", "nexuscli siase afis -m octubre -d", afis)
        captura("siase-historial", "nexuscli siase historial", s.correr("siase", "historial"))
        captura("siase-horario", "nexuscli siase horario", s.correr("siase", "horario"))
        captura("siase-kardex", "nexuscli siase kardex", s.correr("siase", "kardex"))
        s.siase.encuestas = ["Encuesta de servicios escolares"]
        captura("siase-estado", "nexuscli siase estado", s.correr("siase", "estado"))
        captura("siase-recibo", "nexuscli siase recibo", s.correr("siase", "recibo"))

        # Para el banner, las columnas que caben en un cuadro de 6x6.
        corto = lambda salida, n: "\n".join(
            _SGR.sub(lambda m: m.group(0), l) for l in salida.splitlines()[:n])
        banner([
            ("nexuscli tareas", corto(tareas, 14)),
            ("nexuscli siase afis -d", corto(afis, 12)),
            ("nexuscli novedades", corto(novedades, 12)),
        ])



if __name__ == "__main__":
    main()

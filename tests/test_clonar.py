import json

import httpx
import pytest

from nexuscli.clonar import Clonador, arreglar_mojibake, liga_md, nombre_archivo
from nexuscli.markdown import html_a_md
from nexuscli.nexus import Curso

PDF_A = b"%PDF guia" * 10
PDF_B = b"%PDF lectura" * 7
PDF_C = b"%PDF otra copia" * 5


def doc(doc_id, nombre, contenido, carpeta="F"):
    return {"DocumentoId": doc_id, "Nombre": nombre, "Extension": ".pdf", "Peso": len(contenido),
            "URL": f"Contenedores {carpeta}/Contenedor_1/{doc_id}.pdf"}


@pytest.fixture
def curso_falso(fake):
    fake.on("Estructura/ConsultarEstructura", {"Estructura": {"Etapas": [
        {"EtapaId": 10, "Posicion": 2, "Evidencias": [
            {"EvidenciaId": 501, "EntregaExtemporanea": False, "EntregarDocumentos": True, "EntregarRecursoExterno": True},
        ]}],
        "ProductoIntegrador": None}})
    fake.on("Portafolio/ConsultarPortafolio", {"ElementosEvaluables": [{
        "TipoElementoId": 1, "ElementoId": 501, "EtapaId": 10, "Posicion": 4, "Nombre": "Evidencia 2. Videoclip",
        "Valor": 8.0, "FechaInicio": "2026-09-03T15:00:00", "FechaFin": "2026-10-12T23:59:00",
        "FechaLimite": "2026-10-11T23:59:00", "EnEquipo": True, "EquipoId": 3, "UsaRubrica": True,
        "Calificacion": {"Valor": 75.0, "Rubrica": [{"CriterioNivelDominioId": 902}]},
        "Entregas": [], "Retroalimentaciones": [{"RetroalimentacionId": 1, "Descripcion": "Bien, faltó APA.",
                                                 "FechaModificacion": "2026-09-14T16:21:00"}],
    }]})
    fake.on("Estructura/ConsultarDetalleEvidencia", {"Evidencia": {"Contenidos": [
        {"Titulo": "Instrucción general", "Posicion": 0,
         "Descripcion": "<p>1.&nbsp;Lee la <strong>guía </strong>.</p><p>2. Revisa:</p><p>• una</p><p>• dos</p>"
                        '<p><img src="https://plataformanexus.uanl.mx/Contenedores G2/c/foto 1.png"></p>'},
    ], "Tema": [{"TemaId": 77, "Nombre": "Foro de dudas", "Mensaje": "<p>Pregunten aquí</p>"}]}})

    def recursos(req):
        body = json.loads(req.content)
        if body.get("ElementoId"):
            return httpx.Response(200, json={"Recursos": {
                "RecursoArchivos": [
                    {"Posicion": 1, "MostrarEstudiante": True, "Documento": doc(1001, "GI_Ev02 guía.pdf", PDF_A)},
                    {"Posicion": 2, "MostrarEstudiante": True, "Documento": doc(1002, "Lectura.pdf", PDF_B)},
                    {"Posicion": 3, "MostrarEstudiante": True, "Documento": doc(1003, "Lectura.pdf", PDF_C)},
                ],
                "RecursosExternos": [{"ExternoId": 5, "Titulo": "Genially", "Contenido": "https://view.genial.ly/x",
                                      "Descripcion": "Recurso", "MostrarEstudiante": True}],
                "RecursosTextos": [{"TextoId": 6, "Titulo": "Mckee", "Contenido": "<p>Mckee, R. (pÃ¡g. 1)</p>",
                                    "MostrarEstudiante": True}],
            }})
        return httpx.Response(200, json={"Recursos": {
            "RecursoArchivos": [
                {"MostrarEstudiante": True, "Documento": doc(1001, "GI_Ev02 guía.pdf", PDF_A)},
                {"MostrarEstudiante": True, "Documento": doc(2001, "Compromisos.pdf", PDF_B)},
                {"MostrarEstudiante": False, "Documento": doc(2002, "Oculto.pdf", PDF_C)},
            ]}})

    fake.on("Recurso/ConsultarRecursos", recursos)
    fake.on("Rubrica/ConsultarRubrica", {"Rubrica": {
        "Criterios": [{"CriterioId": 1, "Descripcion": "Portada", "Posicion": 1}],
        "NivelDominios": [{"NivelDominioId": 11, "Nombre": "Excelente", "Posicion": 1},
                          {"NivelDominioId": 12, "Nombre": "Suficiente", "Posicion": 2}],
        "CriterioNivelDominios": [
            {"CriterioNivelDominioId": 901, "CriterioId": 1, "NivelDominioId": 11, "Descripcion": "8 elementos", "Puntos": 10},
            {"CriterioNivelDominioId": 902, "CriterioId": 1, "NivelDominioId": 12, "Descripcion": "6 elementos", "Puntos": 6},
        ]}})
    fake.on("Curso/ConsultarDetalleCurso", {"Curso": {"Modalidad": {"Nombre": "No Escolarizada"},
                                                      "Compromiso": {"Descripcion": "<p>a. Entregar a tiempo.</p>"}}})
    fake.on("ProgramaAnalitico/ConsultarProgramaAnalitico", {"ProgramaAnalitico": {
        "Archivo": {"Estado": True, "Documento": doc(3001, "PA_ANÁLISIS.pdf", PDF_A)}}})
    fake.on("Aviso/ConsultarAvisos", {"Avisos": []})
    archivos = {"1001": PDF_A, "1002": PDF_B, "1003": PDF_C, "2001": PDF_B, "2002": PDF_C, "3001": PDF_A}

    def descarga(req):
        name = str(req.url).rsplit("/", 1)[-1]
        if name.endswith(".png"):
            return httpx.Response(200, content=b"PNG")
        return httpx.Response(200, content=archivos[name.removesuffix(".pdf")])

    fake.on("plataformanexus.uanl.mx/Contenedores", descarga)
    return Curso(id=100001, nombre="Análisis audiovisual | AGO26 | 101", profesores=[{"Nombre": "OFELIA"}],
                 inicio="2026-08-03T08:00:00", fin="2026-12-18T23:59:00",
                 raw={"Bienvenida": {"Contenido": "<p><strong>Estimado estudiante:</strong></p>"}})


def descargas(fake):
    return [r for r in fake.requests if r.method == "GET"]


def test_clonar_curso_completo(nx, fake, curso_falso, tmp_path):
    destino = tmp_path / "anau"
    r = Clonador(nx, destino, personal=True, log=lambda _m: None).curso(curso_falso, comando="nexuscli clonar -c 100001")
    t = destino / "2.4"

    ins = (t / "instrucciones.md").read_text()
    assert ins.startswith("# 2.4 · Evidencia 2. Videoclip")
    assert "| Cierra | dom 11 oct 2026 23:59 (Nexus también marca lun 12 oct 2026 23:59; vale la más temprana) |" in ins
    assert "1. Lee la **guía**." in ins
    assert "2. Revisa:\n   - una\n   - dos" in ins
    assert "![imagen](<img/foto 1.png>)" in ins
    assert (t / "img" / "foto 1.png").read_bytes() == b"PNG"
    assert "**Foro de dudas** (tema 77" in ins

    # Mismo nombre, distinto documento: el segundo no pisa al primero.
    assert (t / "Lectura.pdf").read_bytes() == PDF_B
    assert (t / "Lectura (2).pdf").read_bytes() == PDF_C
    rec = (t / "recursos.md").read_text()
    assert "[Lectura (2).pdf](<Lectura (2).pdf>)" in rec
    assert "[Genially](https://view.genial.ly/x) · Recurso" in rec
    assert "Mckee, R. (pág. 1)" in rec  # mojibake corregido

    rub = (t / "rubrica.md").read_text()
    assert "**Obtuviste 6 de 10 = 60 %**" in rub
    assert "| Portada | 10 | **6 ✓** |" in rub
    retro = (t / "retroalimentacion.md").read_text()
    assert "**Calificación:** 75 / 100 · 6 de 8 pts" in retro and "Bien, faltó APA." in retro

    gen = (destino / "generales" / "README.md").read_text()
    assert "PA_ANÁLISIS.pdf" in gen
    assert "Compromisos.pdf" in gen
    assert "GI_Ev02" not in gen          # ya está en la actividad
    assert "Oculto.pdf" not in gen       # MostrarEstudiante false
    assert "Compromiso del estudiante" in (destino / "generales" / "bienvenida.md").read_text()

    idx = (destino / "README.md").read_text()
    assert "Para actualizarla: `nexuscli clonar -c 100001`." in idx
    assert "| [2.4](2.4/instrucciones.md) | Evidencia 2. Videoclip |" in idx

    man = json.loads((destino / ".nexuscli.json").read_text())
    assert man["archivos"]["2.4/GI_Ev02 guía.pdf"]["documento_id"] == 1001
    assert not r.errores
    # 5 documentos + 1 imagen; GI_Ev02 se bajó una vez (en la tarea) y no se repitió en generales.
    assert len([x for x in descargas(fake) if "1001" in str(x.url)]) == 1


def test_resincronizar_no_baja_nada_y_respeta_lo_ajeno(nx, fake, curso_falso, tmp_path):
    destino = tmp_path / "anau"
    Clonador(nx, destino, log=lambda _m: None).curso(curso_falso)
    antes = len(descargas(fake))
    (destino / "2.4" / "mis notas.txt").write_text("notas")

    r = Clonador(nx, destino, log=lambda _m: None).curso(curso_falso)
    assert len(descargas(fake)) == antes
    assert not r.bajados and r.sin_cambio >= 5
    assert r.escritos == ["2.4/recursos.md"]  # solo cambia por el archivo nuevo
    assert "[mis notas.txt](<mis notas.txt>)" in (destino / "2.4" / "recursos.md").read_text()
    assert (destino / "2.4" / "mis notas.txt").read_text() == "notas"


def test_adopta_copias_previas_y_no_pisa_archivos_distintos(nx, fake, curso_falso, tmp_path):
    destino = tmp_path / "anau"
    (destino / "2.4").mkdir(parents=True)
    (destino / "2.4" / "GI_Ev02 guía.pdf").write_bytes(PDF_A)          # copia idéntica hecha a mano
    (destino / "2.4" / "Lectura.pdf").write_bytes(b"mi version")       # archivo ajeno
    Clonador(nx, destino, log=lambda _m: None).curso(curso_falso)
    assert not any(str(x.url).endswith("/1001.pdf") for x in descargas(fake))  # adoptada, no se bajó
    assert (destino / "2.4" / "Lectura.pdf").read_bytes() == b"mi version"
    assert (destino / "2.4" / "Lectura (Nexus).pdf").read_bytes() == PDF_B
    man = json.loads((destino / ".nexuscli.json").read_text())
    assert man["archivos"]["2.4/GI_Ev02 guía.pdf"]["documento_id"] == 1001


def test_nombres():
    assert arreglar_mojibake("pÃ¡g. 2") == "pág. 2"
    assert arreglar_mojibake("Análisis") == "Análisis"
    assert arreglar_mojibake("Análisis pÃ¡g. Ã©xito ¿qué?") == "Análisis pág. éxito ¿qué?"
    assert nombre_archivo("a/b: c?.pdf") == "a-b- c-.pdf"
    assert nombre_archivo("Alegoría y símbolo en el cine..pdf") == "Alegoría y símbolo en el cine..pdf"
    assert nombre_archivo(".oculto.pdf") == "oculto.pdf"
    largo = nombre_archivo("é" * 300 + ".pdf")
    assert len(largo.encode()) <= 240 and largo.endswith(".pdf")
    assert liga_md("2.4/recursos.md") == "2.4/recursos.md"
    assert liga_md("GI Ev (1).pdf") == "<GI Ev (1).pdf>"


def test_markdown_tablas_y_ligas():
    html = ("<h2>Criterios</h2><table><tr><th>Criterio</th><th>Pts</th></tr><tr><td>Portada</td><td>10</td></tr></table>"
            '<p>Ver <a href="https://x.mx/a b">la guía</a> y <a href="https://y.mx">https://y.mx</a><br>fin</p>'
            "<ol><li>uno<ul><li>sub</li></ul></li><li>dos</li></ol>")
    md = html_a_md(html)
    assert "#### Criterios" in md
    assert "| Criterio | Pts |\n|---|---|\n| Portada | 10 |" in md
    assert "[la guía](https://x.mx/a%20b)" in md and "<https://y.mx>" in md
    assert "y.mx>  \nfin" in md
    assert "1. uno\n  - sub\n2. dos" in md

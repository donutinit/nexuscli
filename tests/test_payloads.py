"""Las peticiones que modifican Nexus deben ser idénticas a las del Angular."""

import time

import httpx
import pytest

from nexuscli.client import NexusError, Sesion
from tests.conftest import json_body, multipart_fields


def test_entrega_individual_manda_el_formdata_del_angular(nx, fake, tarea_equipo, archivo):
    fake.on("Tarea/ActualizarEntregaDocumento", {"Entrega": {"EntregaId": 1}})
    nx.subir_archivo(tarea_equipo, archivo, equipo_id=None)

    (req,) = fake.calls("Tarea/ActualizarEntregaDocumento")
    assert req.headers["Token"] == "TOK"
    assert req.headers["AreaAcademicaId"] == "56"
    assert req.headers["RolId"] == "5"
    assert req.headers["DocumentoId"] == "0"
    assert req.headers["Content-Type"].startswith("multipart/form-data")
    assert multipart_fields(req) == [
        ("Documento", "%PDF-1.4 prueba"),
        ("EntregaId", "0"),
        ("TipoElementoId", "1"),
        ("ElementoId", "5000047"),
        ("EnEquipo", "false"),
        ("Estado", "true"),
        ("NombreDocumento", "Resumen_equipo6.pdf"),
        ("CursoId", "100002"),
    ]
    assert 'filename="Resumen_equipo6.pdf"' in req.content.decode()


def test_entrega_en_equipo_sube_a_la_carpeta_y_vincula(nx, fake, tarea_equipo, archivo):
    fake.on("Equipo/ActualizarEquipoArchivo", {"Archivo": {"DocumentoId": 999, "Nombre": archivo.name}})
    fake.on("Tarea/VincularEntregaEquipo", {"Entrega": {"EntregaId": 5}})
    nx.subir_archivo(tarea_equipo, archivo, equipo_id=90006)

    (subida,) = fake.calls("Equipo/ActualizarEquipoArchivo")
    assert multipart_fields(subida) == [
        ("Documento", "%PDF-1.4 prueba"),
        ("EntregaId", "0"),
        ("TipoElementoId", "1"),
        ("ElementoId", "5000047"),
        ("EnEquipo", "true"),
        ("Estado", "true"),
        ("NombreDocumento", "Resumen_equipo6.pdf"),
        ("CursoId", "100002"),
        ("EquipoId", "90006"),
        ("CarpetaId", "0"),
    ]
    (vinculo,) = fake.calls("Tarea/VincularEntregaEquipo")
    assert json_body(vinculo) == {
        "EquipoId": 90006, "EntregaId": 0, "CursoId": 100002, "ElementoId": 5000047,
        "TipoElementoId": 1, "TareaRecursoId": 999, "Estado": True, "TipoEntrega": 1,
    }
    assert [str(r.url).rsplit("/", 2)[-2] for r in fake.requests] == ["Equipo", "Tarea"]


def test_entrega_en_equipo_sin_documento_no_vincula(nx, fake, tarea_equipo, archivo):
    fake.on("Equipo/ActualizarEquipoArchivo", {"Algo": 1})
    with pytest.raises(NexusError, match="no devolvió el documento"):
        nx.subir_archivo(tarea_equipo, archivo, equipo_id=90006)
    assert not fake.calls("Tarea/VincularEntregaEquipo")


def test_borrar_entrega_documento(nx, fake, tarea_equipo):
    fake.on("Tarea/ActualizarEntregaDocumento", {"Entrega": None})
    entrega = {"EntregaId": 80000001, "TipoEntrega": 1, "EnEquipo": True, "Documento": {"DocumentoId": 1}}
    nx.borrar_entrega(tarea_equipo, entrega)
    (req,) = fake.calls("Tarea/ActualizarEntregaDocumento")
    assert multipart_fields(req) == [
        ("Documento", "null"),
        ("NombreDocumento", "null"),
        ("DocumentoId", "null"),
        ("CursoId", "100002"),
        ("EntregaId", "80000001"),
        ("TipoElementoId", "1"),
        ("ElementoId", "5000047"),
        ("EnEquipo", "true"),
        ("Estado", "0"),
    ]


def test_borrar_entrega_liga(nx, fake, tarea_equipo):
    fake.on("Tarea/ActualizarEntregaRecursoExterno", {"Entrega": {}})
    externo = {"ExternoId": 77, "TipoRecursoExternoId": 2, "Titulo": "video", "Contenido": "https://x", "Estado": True}
    nx.borrar_entrega(tarea_equipo, {"EntregaId": 12, "TipoEntrega": 2, "EnEquipo": False, "RecursoExterno": externo})
    body = json_body(fake.calls("Tarea/ActualizarEntregaRecursoExterno")[0])
    assert body["Entrega"] == {"EntregaId": 12, "TipoElementoId": 1, "ElementoId": 5000047, "Estado": False}
    assert body["RecursoExterno"]["ExternoId"] == 77
    assert body["RecursoExterno"]["Estado"] is False
    assert body["EnEquipo"] is False and body["EquipoId"] == 0


def test_liga_en_equipo_vincula_el_externo(nx, fake, tarea_equipo):
    fake.on("Tarea/ActualizarEntregaRecursoExterno", {"Entrega": {"RecursoExterno": {"ExternoId": 555}}})
    fake.on("Tarea/VincularEntregaEquipo", {})
    nx.entregar_liga(tarea_equipo, "https://youtu.be/x", "Video final", equipo_id=90006)
    body = json_body(fake.calls("Tarea/ActualizarEntregaRecursoExterno")[0])
    assert body["RecursoExterno"] == {
        "ExternoId": 0, "Entregado": False, "Estado": True,
        "TipoRecursoExternoId": 2, "Titulo": "Video final", "Contenido": "https://youtu.be/x",
    }
    assert body["EnEquipo"] is True and body["EquipoId"] == 90006
    vinc = json_body(fake.calls("Tarea/VincularEntregaEquipo")[0])
    assert vinc["TareaRecursoId"] == 555 and vinc["TipoEntrega"] == 2


def test_foro_y_mensajes(nx, fake):
    fake.on("Foro/ActualizarTemaComentario/", {"TemaComentario": {}})
    fake.on("Mensaje/ActualizarMensajeConversacion", {"Conversacion": {}})
    nx.foro_comentar(70002, "Duda sobre la 2.4", padre_id=70010)
    nx.enviar_mensaje(42, "Hola profe")
    tc = json_body(fake.calls("Foro/ActualizarTemaComentario/")[0])["TemaComentario"]
    assert tc["TemaId"] == 70002 and tc["ComentarioPadreId"] == 70010 and tc["TemaComentarioId"] == 0
    m = json_body(fake.calls("Mensaje/ActualizarMensajeConversacion")[0])["MensajeConversacion"]
    assert m == {"Mensaje": "Hola profe", "MensajeConversacionId": 0, "ConversacionId": 42,
                 "EmisorCuentaId": 100200, "Estado": True}


def test_error_de_nexus_se_propaga(nx, fake, tarea_equipo):
    fake.on("Tarea/ConsultarEntregas", {"Code": 1003, "ExceptionType": 3, "Message": "El rol no tiene permitido"})
    with pytest.raises(NexusError) as e:
        nx.entregas(tarea_equipo)
    assert e.value.code == 1003


@pytest.mark.parametrize("codigo", [2004, 2011])
def test_token_expirado_reintenta_una_vez(client, fake, monkeypatch, codigo):
    respuestas = iter([{"Code": codigo, "Message": "Sesión expirada"}, {"Entregas": []}])
    fake.on("Tarea/ConsultarEntregas", lambda req: httpx.Response(200, json=next(respuestas)))
    logins = []

    def login():
        logins.append(1)
        client._sesion = Sesion(token="NUEVO", area_id=56, rol_id=5, expira=time.time() + 3600)
        return client._sesion

    monkeypatch.setattr(client, "login", login)
    client.call("Tarea/ConsultarEntregas", {"CursoId": 1})
    assert logins == [1]
    assert [r.headers["Token"] for r in fake.requests] == ["TOK", "NUEVO"]

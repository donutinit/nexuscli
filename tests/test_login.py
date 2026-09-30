import json

import httpx
import pytest

from nexuscli import config
from nexuscli.client import Client, LoginError
from nexuscli.pace import Pacer
from tests.conftest import FakeNexus

LOGIN_HTML = """<form name="inicio" action="eselcarrera.htm" method="post">
<input type="hidden" NAME="HTMLPrograma" value="">
<input type="hidden" name="HTMLToken" value="abc=">
</form>"""

ESEL_HTML = """<script>
$("#idfrNexus").attr("action", "https://plataformanexus.uanl.mx/#/LoginSIASE?Usu=0x0000beef&Ctrl=aa%2Bbb%20cc%3D&HTMLUsuario=1234567&HTMLTipCve=01");
</script>"""


def _client(fake, tmp_path):
    http = httpx.Client(transport=httpx.MockTransport(fake))
    return Client(pacer=Pacer("off"), state=tmp_path, http=http,
                  credenciales=config.Credenciales("1234567", "secreta", "test"))


def test_login_completo_sin_navegador(tmp_path):
    fake = FakeNexus()
    fake.on("login.htm", LOGIN_HTML)
    fake.on("eselcarrera.htm", ESEL_HTML)
    fake.on("Seguridad/CrearSesionSIASE", {"Sesion": {"AreaAcademicaId": 56, "RolId": 5, "Token": "TKN",
                                                      "Tiempo": {"Restante": 19200}}})
    fake.on("Seguridad/ConsultarPerfil", {"Persona": {"PersonaId": 1, "Nombre": "ANA", "ApellidoPaterno": "LOPEZ",
                                                      "Cuentas": [{"CuentaId": 100200, "NombreUsuario": "1234567"}]}})
    c = _client(fake, tmp_path)
    s = c.login()

    post = fake.calls("eselcarrera.htm")[0]
    form = dict(x.split("=", 1) for x in post.content.decode().split("&"))
    assert form == {"HTMLPrograma": "", "HTMLToken": "abc%3D", "HTMLTipCve": "01",
                    "HTMLUsuCve": "1234567", "HTMLPassword": "secreta"}
    crear = fake.calls("Seguridad/CrearSesionSIASE")[0]
    # Ctrl viene url-encoded y los espacios se vuelven '+', como en LoginSiaseComponent.getToken.
    assert crear.headers["Control"] == "aa+bb+cc="
    assert crear.headers["Usuario"] == "0x0000beef"
    assert crear.headers["UsuarioClave"] == "1234567"
    assert crear.headers["TipoClave"] == "01"
    assert "Token" not in crear.headers
    assert fake.calls("Seguridad/ConsultarPerfil")[0].headers["Token"] == "TKN"

    assert (s.token, s.cuenta_id, s.area_id, s.rol_id) == ("TKN", 100200, 56, 5)
    guardada = json.loads((tmp_path / "sesion.json").read_text())
    assert guardada["token"] == "TKN"
    assert oct((tmp_path / "sesion.json").stat().st_mode & 0o777) == "0o600"


def test_login_rechazado(tmp_path):
    fake = FakeNexus()
    fake.on("login.htm", LOGIN_HTML)
    fake.on("eselcarrera.htm", "<html><body>Usuario o contraseña incorrectos. Intente de nuevo.</body></html>")
    with pytest.raises(LoginError, match="incorrect"):
        _client(fake, tmp_path).login()
    assert not fake.calls("Seguridad/CrearSesionSIASE")


def test_credenciales_formatos(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_USUARIO", raising=False)
    monkeypatch.delenv("NEXUS_PASSWORD", raising=False)
    f = tmp_path / "cred"
    f.write_text("USER=1234567\nPASS='con espacio'\n")
    f.chmod(0o600)
    monkeypatch.setenv("NEXUS_CREDENCIALES", str(f))
    c = config.load_credentials()
    assert (c.usuario, c.password) == ("1234567", "con espacio")

    f.chmod(0o644)
    with pytest.raises(config.CredencialesError, match="chmod 600"):
        config.load_credentials()

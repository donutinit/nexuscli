# nexuscli: guía para agentes

CLI de Python para Nexus y SIASE de la UANL. Existe para que un agente (Claude, Codex, OpenCode)
los use por la persona: leer tareas, calificaciones y comentarios, entregar, publicar, clonar el
material de las materias, ver AFIs con cupo, kardex, horario, pagos y trámites escolares, y
pre-registrarse en AFIs. `AGENTS.md` es el archivo canónico y `CLAUDE.md` tiene el mismo contenido. Si
existe `CLAUDE.local.md` (fuera de git), léelo también: trae notas de la máquina.

## reglas

- Leer es libre. No entregues, borres, publiques en el foro, respondas comentarios ni mandes
  mensajes si la persona no lo pidió de forma explícita: lo ve el profesor o el grupo y no se
  deshace limpio.
- Los comandos que modifican Nexus muestran un resumen y piden confirmación. Usa `-y` solo
  cuando la persona ya aprobó ese resumen concreto.
- Lo mismo con SIASE: `nexuscli siase inscribir` y `liberar` solo si la persona lo pidió, para
  esa AFI concreta.
- Nunca respondas por la persona las preguntas que SIASE pone antes de su menú (incorporación al
  IMSS, encuestas, datos personales). Las consultas funcionan igual; esas se contestan en la web.
- `nexuscli api` es para métodos `Consultar*`. `--escribir` solo si la persona lo pidió.
- No uses `--pace off` contra el servidor real; es para tests.
- Para leer resultados usa `--json`.
- Credenciales, sesión y descargas no van a git ni se copian a otro lado.
- `nexuscli siase datos` trae NSS, CURP, domicilio y demás. Úsalo solo si la persona necesita un
  dato de ahí, pide la sección concreta con `-s` y no lo copies a archivos, commits, issues ni
  mensajes. Lo mismo con recibos, adeudos y calificaciones: se leen para contestarle a la persona,
  no se guardan en otro lado.
- Las encuestas y los trámites de SIASE solo se leen; contestarlos o pedirlos se hace en la web.

## uso

```sh
nexuscli doctor                         # credenciales, sesión y API
nexuscli cursos                         # materias con su código y su último clon
nexuscli tareas [-p] [-s] [-c CURSO]    # -p pendientes, -s esta semana
nexuscli tarea 2.4 -c anau              # instrucciones, entregas y comentarios
nexuscli novedades                      # lo nuevo desde la última vez
nexuscli calificaciones | comentarios | avisos | equipo | recursos | foro [TEMA] | mensajes [ID]
nexuscli entregar TAREA ARCHIVO... [--individual]
nexuscli liga TAREA URL -t TITULO
nexuscli borrar TAREA [ENTREGA_ID...|--todas]
nexuscli clonar -c CURSO -o CARPETA [--personal]
nexuscli codigo CURSO CODIGO            # código corto de materia
nexuscli api Dominio/ConsultarAlgo '{"CursoId": 1}'
nexuscli novedades --siase              # suma calificaciones, parciales, AFIs, adeudos, encuestas y trámites

nexuscli siase afis [-d] [-m MES] [-a AREA] [-b TEXTO] [-s] [--nuevas]
nexuscli siase afi ID | inscribir ID | liberar ID
nexuscli siase historial | kardex [-p] | periodos | calificaciones [-p PERIODO] | horario [--lista] | perfil
nexuscli siase estado                   # tablero: situación, inscripción, recibo, adeudos, beca, documentos...
nexuscli siase situacion | inscripcion | recibo [--intersemestral] | recibos | adeudos | beca
nexuscli siase documentos | tramites | encuestas | evaluaciones [-p PERIODO] | datos [-s SECCION]
```

Las tareas se nombran por su número (`2.4`, `PIA`), su id o un pedazo del nombre; las materias,
con `-c` y un pedazo del nombre, su id o su código.

## código

- `src/nexuscli/client.py`: login por SIASE, sesión, HTTP y reintento si la sesión dejó de
  valer (códigos 2004 y 2011).
- `src/nexuscli/nexus.py`: la única capa que conoce los endpoints. Si Nexus cambia, se
  arregla aquí; `docs/api.md` es la referencia.
- `src/nexuscli/cli.py`: comandos. `clonar.py` y `markdown.py`: la copia local. `materias.py`:
  códigos, clones y avisos de cierre. `store.py`: lo visto por `novedades`. `pace.py`: pausas.
  `estilo.py`: color. `texto.py`: fechas y texto. `config.py`: rutas y credenciales.
- `src/nexuscli/siase.py`: sesión de SIASE (`HTMLtrim`), parsers puros `parse_*` y pre-registro de
  AFIs; `dom.py` es el árbol HTML tolerante que usan; `cli_siase.py`, los comandos.
  `docs/siase.md` es la referencia. En SIASE pre-registrar y liberar son la misma petición: no
  quites los candados que revisan el historial antes y después. `siase_escolar.py` tiene las
  consultas escolares (situación, pagos, trámites, datos), con sus parsers y la clase `Escolar`.
- Tests: `uv run pytest`, sin red. `tests/siase_falso.py` es un SIASE de mentira con la
  estructura de las páginas reales; úsalo si cambias un parser. `tests/test_payloads.py` fija los cuerpos de escritura; si
  cambias uno, que sea porque el frontend de Nexus cambió.
- Capturas del README: `uv run python docs/capturas/generar.py` (necesita Chromium). Usan datos
  inventados de `docs/capturas/demo.py`: nunca pongas datos reales de nadie en el repo.
- Texto en español: sin rayas largas ni cortas y con comillas rectas.
- Commits de una línea en español.

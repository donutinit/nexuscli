<p align="center">
  <img src="docs/img/banner.png" width="100%" alt="hoja de contacto de nexuscli: el nombre y tres cuadros con capturas de la terminal">
</p>

<p align="center">
  <sub><b>nexus y siase desde la terminal.</b> tareas, entregas en equipo, comentarios del profe, el material de cada materia, afis con cupo, kardex, horario y pagos, sin abrir el navegador.</sub>
</p>

<p align="center">
  <img alt="python 3.12" src="https://img.shields.io/badge/-python%203.12-1b1a1e?style=flat-square&logo=python&logoColor=d8cfc0">&nbsp;
  <img alt="sin navegador" src="https://img.shields.io/badge/-sin%20navegador-5c6b52?style=flat-square">&nbsp;
  <img alt="hecho para agentes" src="https://img.shields.io/badge/-hecho%20para%20agentes-d9873f?style=flat-square">&nbsp;
  <a href="LICENSE"><img alt="licencia MIT" src="https://img.shields.io/badge/-licencia%20MIT-8c3a4a?style=flat-square"></a>&nbsp;
  <a href="https://github.com/donutinit/nexuscli/actions/workflows/tests.yml"><img alt="tests" src="https://img.shields.io/github/actions/workflow/status/donutinit/nexuscli/tests.yml?style=flat-square&label=tests&labelColor=1b1a1e&color=5c6b52"></a>
</p>

<p align="center"><img src="docs/img/rule.svg" width="100%" alt=""></p>

`nexuscli` trabaja con las dos plataformas escolares de la UANL: [Nexus](https://plataformanexus.uanl.mx), donde están las clases, y [SIASE](https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/login.htm), donde están las AFIs, el kardex, las calificaciones, el horario y los trámites escolares. Entra con tu matrícula y tu contraseña de SIASE sin abrir un navegador, así que lo puedes usar tú en la terminal o un agente como Claude o Codex que trabaje por ti.

<p align="center">
  <img src="docs/img/tareas.png" width="94%" alt="nexuscli tareas: tabla con el estado, el cierre, los puntos y la modalidad de cada tarea de dos materias">
</p>

## qué hace

- Enseña tus tareas de todas las materias: estado, cierre, valor y si son en equipo.
- Abre una tarea con sus instrucciones completas, tus entregas y los comentarios del profe.
- Entrega archivos o ligas a tu nombre o por tu equipo, y borra entregas.
- Consulta calificaciones, avisos, foro y mensajes, y publica o responde en ellos.
- Te dice qué hay de nuevo desde la última vez que preguntaste.
- Copia el material de una materia a tu computadora: instrucciones, rúbricas, lecturas y archivos.
- Lista las AFIs de cada mes con su cupo, te pre-registra o libera tu lugar y lleva la cuenta de cuántas oficiales llevas.
- Lee tu kardex, tus calificaciones finales y parciales de cada periodo y tu horario.
- Junta en un tablero tu situación escolar, el día de inscripción, el recibo, adeudos, beca, documentos, trámites y encuestas.

## instalación

Necesitas Python 3.12 o más nuevo. Con [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/donutinit/nexuscli
```

Con pipx:

```sh
pipx install git+https://github.com/donutinit/nexuscli
```

Para trabajar en el código:

```sh
git clone https://github.com/donutinit/nexuscli && cd nexuscli
uv sync
uv run nexuscli --help
```

Su única dependencia es [httpx](https://www.python-httpx.org).

## credenciales

`nexuscli` lee tu matrícula y tu contraseña de SIASE de `~/.config/nexuscli/credenciales`:

```sh
mkdir -p ~/.config/nexuscli
cat > ~/.config/nexuscli/credenciales <<'EOF'
NEXUS_USUARIO=1234567
NEXUS_PASSWORD=tu contraseña de SIASE
EOF
chmod 600 ~/.config/nexuscli/credenciales
nexuscli doctor
```

Si otro usuario de la computadora puede leer ese archivo, `nexuscli` se niega a usarlo. También acepta las variables de entorno `NEXUS_USUARIO` y `NEXUS_PASSWORD`, o `NEXUS_CREDENCIALES` con otra ruta. `nexuscli doctor` revisa las credenciales, la sesión y que el API responda.

## el día a día

```sh
nexuscli tareas               # todas, ordenadas por fecha de cierre
nexuscli tareas -p            # solo las que faltan
nexuscli tareas -s -c seim    # las que cierran esta semana en una materia
nexuscli tarea 2.2 -c seim    # instrucciones, entregas y comentarios
nexuscli calificaciones
nexuscli comentarios          # la retroalimentación de los profes
nexuscli avisos
nexuscli novedades
```

Las tareas se nombran como en la web (`2.2`, `PIA`), por su id o por un pedazo del nombre. Las materias van con `-c` y un pedazo del nombre, su id o su código. Si algo coincide con más de una, `nexuscli` te enseña las opciones.

`novedades` enseña lo que cambió desde la última vez que lo corriste: comentarios del profe, calificaciones, avisos, mensajes del foro, tareas nuevas y fechas que se movieron. La primera vez solo registra lo que ya existe, y una materia nueva aparece en una sola línea.

<p align="center">
  <img src="docs/img/novedades.png" width="82%" alt="nexuscli novedades: un comentario del profe, una calificación, un aviso y un mensaje del foro">
</p>

<p align="center">
  <img src="docs/img/tarea.png" width="64%" alt="nexuscli tarea: encabezado de la tarea, instrucciones con pasos numerados y viñetas, y entregas">
</p>

## entregar

```sh
nexuscli entregar 2.2 EQUIPO3_ACT2.2.pdf -c seim   # en tareas de equipo, entrega por el equipo
nexuscli entregar 2.2 borrador.pdf --individual    # solo a tu nombre
nexuscli liga 2.3 https://youtu.be/... -t "Video final"
nexuscli entregas 2.2                              # lo que ya está entregado
nexuscli borrar 2.2 555                            # por id de entrega, o --todas
```

Antes de subir algo, `nexuscli` enseña la tarea, tu equipo, cuándo cierra (y si ya cerró) y lo que ya estaba entregado, y te pide confirmar. Con `-y` no pregunta. Sin terminal, desde un script por ejemplo, no sigue si no le pasas `-y`. En una tarea de equipo hace lo mismo que la web: sube el archivo a la carpeta del equipo y lo vincula como entrega.

<p align="center">
  <img src="docs/img/entregar.png" width="74%" alt="nexuscli entregar: resumen de la tarea y del equipo, confirmación y la entrega registrada">
</p>

Publicar en el foro (`comentar`), responder un comentario del profe (`responder`) y mandar mensajes (`enviar`, `escribir`) también piden confirmación.

## clonar el material de una materia

```sh
nexuscli clonar -c seim -o ~/escuela
```

<p align="center">
  <img src="docs/img/clonar.png" width="94%" alt="nexuscli clonar: una línea por actividad con sus archivos, enlaces, lecturas y rúbrica">
</p>

Crea `~/escuela/seim/` con una carpeta por actividad y una de generales:

```text
seim/
├── README.md             índice de actividades
├── generales/            programa, bienvenida, avisos y lecturas
├── 2.2/
│   ├── instrucciones.md
│   ├── rubrica.md
│   ├── recursos.md       archivos, enlaces y lecturas
│   ├── GI_Act 2.2 guía de la actividad.pdf
│   └── Barthes - Retórica de la imagen.pdf
├── 2.3/ …
└── pia/
```

Si lo vuelves a correr, solo baja lo que falta o cambió en Nexus. Nunca borra: los archivos que agregues a una carpeta se quedan ahí y aparecen en su `recursos.md`. Con `--personal` suma tu calificación, el nivel que te marcó el profe en cada criterio de la rúbrica, sus comentarios y tus entregas.

<details>
<summary>así queda una rúbrica</summary>

> **Rúbrica · 2.2 · Act 2.2 Storyboard comentado de una secuencia.**
>
> 3 criterios · niveles: Excelente, Suficiente, Insuficiente · máximo 100 puntos
>
> | Criterio | Excelente | Suficiente | Insuficiente |
> | --- | ---: | ---: | ---: |
> | Selección de la secuencia | 30 | 20 | 10 |
> | Storyboard | 30 | 20 | 10 |
> | Comentario semiótico | 40 | 25 | 10 |
>
> **1. Selección de la secuencia**
>
> - **Excelente · 30**: Secuencia pertinente y justificada.
> - **Suficiente · 20**: Pertinente sin justificar.
> - **Insuficiente · 10**: No se justifica.

</details>

## materias y códigos

Cada materia puede tener un código corto, como `seim` o `guci`, que sirve en `-c` y le da nombre a su carpeta al clonar. `nexuscli cursos` enseña el código de cada materia, o una propuesta con `?` si todavía no tiene. `nexuscli codigo <materia> <código>` lo confirma y `nexuscli codigo --aceptar` acepta todas las propuestas. Los códigos se guardan en `~/.config/nexuscli/materias`.

<p align="center">
  <img src="docs/img/cursos.png" width="82%" alt="nexuscli cursos: materias con su código, profesor, fecha de fin y último clon">
</p>

Nexus deja de mostrar una materia poco después de que termina. Desde tres semanas antes, `novedades`, `tareas` y `cursos` avisan si no la has clonado o si tu copia tiene más de una semana, y te dan el comando para actualizarla.

## siase

```sh
nexuscli siase afis -d                              # las de este mes que tienen lugares
nexuscli siase afis -m octubre -a culturales -b cine
nexuscli siase afi 4102                             # descripción, cupo y lugar
nexuscli siase inscribir 4102                       # pre-registro, con confirmación
nexuscli siase liberar 4102
nexuscli siase historial                            # cuántas oficiales llevas de cuántas
nexuscli siase kardex -p                            # solo las materias que no has aprobado
nexuscli siase calificaciones -p "ene jun 2026"
nexuscli siase horario
nexuscli siase estado                               # tablero de todo lo escolar
```

<p align="center">
  <img src="docs/img/siase-afis.png" width="94%" alt="nexuscli siase afis: AFIs de octubre con su cupo, fechas, área y organizador">
</p>

`afis` pinta el cupo en verde, en naranja cuando quedan menos de diez lugares y como "lleno" en rojo. Esconde los eventos que ya terminaron; `-s` deja solo los de los próximos siete días y `--nuevas`, los que no habías visto. Los eventos en los que ya estás llevan ✓. El mes va por número o por nombre, y el área por un pedazo de su nombre.

<p align="center">
  <img src="docs/img/siase-historial.png" width="94%" alt="nexuscli siase historial: 3 de 14 AFIs oficiales con una barra de avance y la lista de eventos">
</p>

`inscribir` hace lo mismo que la página: selecciona el evento y guarda el pre-registro. En SIASE, pre-registrarse y liberar un lugar son la misma petición, así que `nexuscli` revisa tu historial antes y después. No te pre-registra si ya estabas o si ya no hay cupo, no libera si no estás o si tu asistencia ya contó, y al terminar te dice si SIASE lo confirma.

<p align="center">
  <img src="docs/img/siase-horario.png" width="72%" alt="nexuscli siase horario: la semana por hora con la abreviatura y el salón de cada materia">
</p>

`horario` pinta la semana por hora con la abreviatura de cada materia y su salón, y abajo las materias con su grupo, modalidad, créditos y oportunidad. De paso guarda las abreviaturas, y `nexuscli cursos` las usa para proponer los códigos de tus materias de Nexus.

<p align="center">
  <img src="docs/img/siase-kardex.png" width="80%" alt="nexuscli siase kardex: materias por semestre con sus oportunidades y la calificación final">
</p>

### consultas escolares

```sh
nexuscli siase estado                     # todo lo de abajo en una pantalla
nexuscli siase situacion                  # situación, tipo de inscripción y foto
nexuscli siase inscripcion                # día y hora para inscribirte
nexuscli siase recibo [--intersemestral]  # conceptos del recibo y si ya está pagado
nexuscli siase recibos                    # recibos internos
nexuscli siase adeudos
nexuscli siase beca
nexuscli siase documentos                 # si a tu expediente le falta algo
nexuscli siase tramites                   # trámites con el Departamento Escolar y de Archivo
nexuscli siase encuestas
nexuscli siase evaluaciones -p "ago dic 2026"
nexuscli siase datos -s domicilio
```

<p align="center">
  <img src="docs/img/siase-estado.png" width="94%" alt="nexuscli siase estado: semestre, situación, día de inscripción, recibo pagado, adeudos, beca, documentos, trámites, una encuesta pendiente y AFIs oficiales">
</p>

`estado` lee nueve páginas del menú de SIASE y las junta en una vista. Lo que ya está en orden sale en verde, lo que te toca hacer en naranja y los adeudos en rojo. Si una página falla, esa fila lo dice y las demás salen igual.

<p align="center">
  <img src="docs/img/siase-recibo.png" width="80%" alt="nexuscli siase recibo: conceptos del recibo del semestre con su importe, el total y la fecha de pago">
</p>

`datos` enseña lo que SIASE tiene de ti: NSS, CURP, domicilio y demás, sin los campos vacíos. `-s` deja solo una sección. Es información sensible: no la pegues en un issue ni en un chat.

`encuestas`, `tramites`, `beca` y `documentos` solo leen. Contestar una encuesta o pedir un trámite se hace en la web.

`nexuscli novedades --siase` suma las calificaciones finales nuevas, las parciales, la asistencia registrada en tus AFIs, las AFIs nuevas con cupo, los adeudos, las encuestas nuevas y los cambios de estatus de tus trámites.

A veces SIASE bloquea su menú hasta que respondas una pregunta, como la de la incorporación al IMSS. `nexuscli` puede leer de todos modos, pero esa pregunta la contestas tú en la web. [docs/siase.md](docs/siase.md) explica cada página que lee.

## para agentes

`nexuscli` se hizo para que un agente de IA pueda usar Nexus y SIASE por la persona. Todos los comandos aceptan `--json` y regresan la información completa:

```sh
nexuscli tareas -p --json | jq '.[] | {clave, nombre, fin, estado}'
nexuscli api Curso/ConsultarDetalleCurso '{"CursoId": 100001}'
```

Lo mismo vale para `nexuscli siase ...`.

`nexuscli api` llama cualquier método de lectura (`Consultar*`) del API de Nexus. Los que modifican algo exigen `--escribir` y confirmación. Leer no tiene restricciones; entregar, borrar, publicar o pre-registrarse en una AFI necesita `-y`, y [AGENTS.md](AGENTS.md) le pide al agente usarlo solo cuando la persona se lo pidió.

## cómo funciona

Para entrar, `nexuscli` pide la página de SIASE, manda el formulario y saca de la respuesta el parámetro con el que SIASE abre Nexus; `Seguridad/CrearSesionSIASE` lo cambia por un token. Todo es HTTP, sin navegador.

Cada operación es un `POST` a `https://api.nexus.uanl.mx/WebApi/<Dominio>/<Método>` con el token en los headers. Los cuerpos copian los que manda el frontend de Nexus, y [docs/api.md](docs/api.md) documenta los que usa `nexuscli`.

La sesión dura unas cinco horas y se renueva sola. Nexus admite una sola sesión por usuario: si `nexuscli` entra, se cierra la del navegador, y al revés. Cuando pasa, `nexuscli` vuelve a entrar solo.

SIASE no tiene API: `nexuscli` lee su HTML. Su sesión es un campo oculto (`HTMLtrim`) que se vence tras 30 minutos sin uso, y `nexuscli` entra de nuevo cuando hace falta. [docs/siase.md](docs/siase.md) explica cada página.

Entre una llamada y otra espera un tiempo al azar, casi siempre alrededor de un segundo y de vez en cuando varios, sacado de la entropía del sistema operativo. `--pace` elige entre `rapido`, `normal` y `lento`.

## qué guarda y dónde

| archivo | contenido |
| --- | --- |
| `~/.config/nexuscli/credenciales` | tu matrícula y tu contraseña |
| `~/.config/nexuscli/materias` | los códigos de materia |
| `~/.local/state/nexuscli/sesion.json` | el token de la sesión de Nexus |
| `~/.local/state/nexuscli/siase.json` | la sesión de SIASE y las claves de tu carrera |
| `~/.local/state/nexuscli/siase-materias.json` | las abreviaturas de tus materias en SIASE |
| `~/.local/state/nexuscli/cache/` | tus materias y la estructura de cada una, por unas horas |
| `~/.local/state/nexuscli/visto.db` | huellas de lo que ya viste, para `novedades` |
| `~/.local/state/nexuscli/clones.json` | dónde y cuándo clonaste cada materia |

Todos tienen permisos 600 dentro de carpetas 700, así que solo tu usuario los lee. Las calificaciones, los comentarios, el kardex, el historial de AFIs, los pagos y tus datos personales se piden cada vez y no se guardan; `visto.db` solo tiene huellas (hashes) para saber qué cambió.

## desarrollo

```sh
uv sync
uv run pytest                            # sin red, contra un Nexus falso
uv run python docs/capturas/generar.py   # regenera las imágenes de este README
```

Las capturas salen del CLI real corriendo contra el Nexus de mentira de [docs/capturas/demo.py](docs/capturas/demo.py) y el SIASE de mentira de [tests/siase_falso.py](tests/siase_falso.py), que también usan los tests. Las materias, profes, compañeros y eventos que aparecen son inventados.

## aviso

`nexuscli` no es de la UANL ni está respaldado por ella. Usa tus propias credenciales, y lo que hagas con él lo registra Nexus igual que si lo hicieras en la página. Si Nexus o SIASE cambian, algo puede dejar de funcionar; [docs/api.md](docs/api.md) y [docs/siase.md](docs/siase.md) son el punto de partida para arreglarlo.

Las lecturas están probadas contra Nexus y SIASE. Entregar, borrar y publicar en Nexus, y pre-registrarse o liberar una AFI en SIASE, copian campo por campo lo que manda cada página y tienen tests, pero todavía no se han probado contra los servidores reales: revisa en la web la primera vez que los uses.

<p align="center"><img src="docs/img/rule.svg" width="100%" alt=""></p>

<p align="center"><sub>licencia MIT · <a href="https://github.com/donutinit">donutinit</a></sub></p>

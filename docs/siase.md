# SIASE

Cómo lee `nexuscli` las AFIs, el kardex, las calificaciones, el horario y las consultas escolares de [SIASE](https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/login.htm). SIASE es una aplicación Progress WebSpeed de hace varios años: no tiene API, así que `nexuscli` lee su HTML. No es documentación oficial y cualquier cambio de SIASE lo puede romper.

Las consultas de esta página están probadas contra SIASE. El pre-registro y la liberación de AFIs copian lo que hace la página y `tests/test_siase.py` los fija contra un SIASE falso, pero todavía no se han probado contra el servidor real.

El proyecto [GDSC-UANL/siase-api](https://github.com/GDSC-UANL/siase-api) mapeó antes varias de estas páginas y sirvió de punto de partida. `nexuscli` no usa su código: es GPL v3 y aquí todo se escribió de nuevo.

## sesión

1. `GET login.htm`. El formulario trae los campos ocultos `HTMLToken` y `HTMLPrograma`.
2. `POST eselcarrera.htm` con esos campos, `HTMLTipCve=01` (alumno), `HTMLUsuCve` (matrícula) y `HTMLPassword`. Es el mismo login con el que `nexuscli` entra a Nexus.

La respuesta trae dos cosas:

- `<input type="hidden" name="HTMLtrim" value="...">`, que funciona como sesión. SIASE no usa cookies.
- una liga por carrera, con sus claves en JavaScript:
  ```
  javascript:self.document.SelCarrera.HTMLCve_Dependencia.value='09999';
             self.document.SelCarrera.HTMLCve_Unidad.value='01'; ...
  ```

Todas las consultas llevan en la URL `HTMLUsuario` (matrícula), `HTMLtrim`, las siete claves de la carrera (`HTMLCve_Dependencia`, `HTMLCve_Unidad`, `HTMLCve_Nivel_Academico`, `HTMLCve_Grado_Academico`, `HTMLCve_Modalidad`, `HTMLCve_Plan_Estudio`, `HTMLCve_Carrera`) y `HTMLTipCve=01`.

La sesión se vence tras 30 minutos sin uso. `nexuscli` la guarda en `~/.local/state/nexuscli/siase.json` y entra de nuevo a los 25 minutos o cuando SIASE responde uno de estos mensajes:

- `Procedimiento restringido, iniciar sesion nuevamente.`
- `El tiempo de inactividad (30 minutos) excedio, iniciar sesion nuevamente.`

Los errores llegan como un `alert('...')` que la página ejecuta al cargar. Muchas páginas también tienen `alert` dentro de funciones de JavaScript que nunca corren solas (por ejemplo "Acceso no Válido."), así que `nexuscli` solo toma en cuenta los que están fuera de funciones.

Las páginas vienen en ISO-8859-1.

Después del login, SIASE puede bloquear el menú hasta que respondas una pregunta (por ejemplo, la incorporación al IMSS). Las consultas de abajo funcionan igual con el menú bloqueado, pero esa pregunta la tiene que responder la persona en la web.

## consultas

Todas son `GET https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/<página>` con los parámetros de sesión.

| página | qué trae |
| --- | --- |
| `maintop.htm` | matrícula, nombre, carrera y plan en el encabezado |
| `delSavePrereg.htm` | las AFIs del mes. Opcionales: `HTMLCveMes=MM` y `HTMLCveArea=N` |
| `delConsRegEven.htm` | tu historial de AFIs y el conteo de oficiales |
| `econkdx01.htm` | el kardex |
| `econcfs01.htm` | los periodos para consultar calificaciones |
| `echalm01.htm` | los periodos para consultar el horario |
| `econeva01.htm` | los periodos para consultar las evaluaciones parciales |

### AFIs

La tabla con `class="TablaLink"` tiene una fila por evento y estas columnas:

| # | columna | notas |
| --- | --- | --- |
| 0 | checkbox | `value` es el id del evento. `disabled` si ya no hay lugares; su `onclick` es `EventoA(...)` o `DelReg(...)` |
| 1 | Organizado por | |
| 2 | Area | ACADEMICAS, INVESTIGACION, CULTURALES, ARTISTICAS, DEPORTIVAS... |
| 3 | Evento | el `title` de la celda trae la descripción completa |
| 4, 5 | Fecha y hora de inicio y fin | `dd/mm/aaaa hh:mm` |
| 6, 7, 8 | Capacidad, Pre-Registro, Disponibles | |

Las áreas y los meses salen de los `<select name="HTMLArea">` y `<select name="HTMLMes">`. El mes que se está viendo viene en `<input name="HTMLCveMes01">`.

### historial

El texto "Total de AFI's con Asistencia Oficial: N" y "Valor AFI por Carrera: M" da cuántas llevas y cuántas pide tu carrera. La tabla tiene estas columnas: evento, área, fecha, asistencia (Si/No), evento oficial (Si/No), número de evento oficial y periodo. La celda del evento separa sus datos con negritas: `<b>5201 Evento:</b>`, `<b>Indicaciones:</b>`, `<b>Recinto:</b>`, `<b>Sede:</b>`, `<b>Dirección:</b>`, `<b>Municipio:</b>`, `<b>Estado:</b>`, `<b>Pais:</b>` y `<b>Organizado por:</b>`.

Ahí aparecen también los eventos en los que estás pre-registrado aunque todavía no pasen.

### kardex

La segunda tabla tiene semestre, modalidad, clave, materia, de la primera a la sexta oportunidad y laboratorio. Además de números aparecen claves como `NC` y `NP`. `nexuscli` toma como calificación final la última oportunidad con algo escrito y cuenta una materia como aprobada si ese valor es un número de 70 o más.

### calificaciones y horario

Las dos van en dos pasos. La página de periodos tiene un formulario `mi_forma` con `<select name="HTMLPeriodo">` y un `<input name="HTMLResill">`. Al elegir un periodo, el JavaScript pone `HTMLTrund` y hace el envío:

```
POST control.p?<parámetros de sesión>
HTMLPeriodo=0x00000000003b9471&HTMLTrund=econcfs02&HTMLResill=<el de la página>
```

`HTMLTrund` es `econcfs02` para calificaciones y `echalm02` para el horario.

- **Calificaciones:** la tabla tiene clave, materia, tipo de inscripción, grupo, fecha, calificación y oportunidad. Mientras el profesor no captura la calificación, la fecha es `?` y la calificación está vacía.
- **Horario:** trae tres tablas. La primera es una cuadrícula con una fila por hora (`7:01 am a<BR> 8:00 am`) y una columna por día, de lunes a sábado. Cada celda es `<b>F-01</b> / CO<br>SEIM<br>201<B> / </B>A105`: fase, tipo, abreviatura, grupo y salón. La segunda es la lista de materias, con clave, nombre, abreviatura, grupo, tipo de oferta, frecuencias, créditos y oportunidad. La tercera tiene el total de horas presenciales y asíncronas.

Las abreviaturas del horario (SEIM, GUCI...) son los nombres cortos que SIASE da a cada materia. `nexuscli` las guarda en `~/.local/state/nexuscli/siase-materias.json` para proponerlas como códigos de materia en Nexus.

## consultas escolares

Son las páginas del menú que no tienen que ver con materias. Van con los mismos parámetros de sesión. Son páginas chicas sin `class` ni `id` útiles, así que los parsers de `siase_escolar.py` ubican cada dato por el texto que lo rodea.

| comando | página | qué lee |
| --- | --- | --- |
| `situacion` | `ecSitEst01.htm` | la identificación virtual: semestre, `SITUACIÓN DEL ESTUDIANTE`, `TIPO DE INSCRIPCIÓN`, `FOTO ACEPTADA` y la división |
| `inscripcion` | `ecohoinsint01.htm` | `Dia de Inscripcion :` y `Hora de Inscripcion :`, con el periodo arriba |
| `adeudos` | `ecavpag04.htm` | una tabla de cuenta, cantidad, concepto y total; la última fila es `Adeudo Total :` |
| `beca` | `bccosobe01.htm` | un mensaje, por ejemplo "No cuenta con una solicitud de beca" |
| `encuestas` | `eenc01.htm` | el `<select name="HTMLEncuesta">`: cada opción distinta de "Seleccione" es una encuesta pendiente |
| `tramites` | `eccontram03.htm` | la tabla de solicitudes (número, documento, fecha, importe, estatus) y un `<select>` con los documentos que se pueden pedir |
| `documentos` | `DEYA+ecCargaDocto01.htm` | el estado del expediente y los documentos que falten |
| `recibo` | `ecBolRec-v02.htm` (`v03` el intersemestral) | periodo, tipo de inscripción, conceptos con su cuenta e importe, total, fecha límite y el bloque "Transacción exitosa" con monto, fecha y estado del pago |
| `recibos` | `ecavpag01.htm` | los recibos internos; cada liga es `javascript:ejecuta('<id>')` y el encabezado de su grupo ("Boletas pagadas") dice su estado |
| `datos` | `edatal01.htm` | una tabla de pares etiqueta y valor con filas de título (IMSS, Datos Generales, Domicilio Local...) |
| `evaluaciones` | `econeva01.htm` y `control.p` | igual que las calificaciones, con `HTMLTrund=econeva02` |

`documentos` es la única que no vive en `wspd_cgi.sh`: la página es `https://deimos.dgi.uanl.mx/cgi-bin/deya.sh/ecCargaDocto01.htm`, con los mismos parámetros.

Sin evaluaciones parciales capturadas, `control.p` responde con un `alert` ("No cuenta con Evaluaciones o Parciales en este periodo."). `nexuscli` lo toma como una lista vacía y no como error.

`datos` trae el NSS, la CURP y el domicilio. `nexuscli` no lo guarda y omite los campos vacíos.

## pre-registro de AFIs

La lista de AFIs está dentro del formulario `mi_forma`. Pre-registrarse en la web tiene dos pasos:

1. Marcar el checkbox de un evento llama `EventoA('delSavePrereg.htm', <id>)`, que envía el formulario con `POST delSavePrereg.htm?<sesión>&HTMLCveEvento=<id>`. La página regresa con ese evento seleccionado y el botón "Guardar Pre Registro" ya apunta a él: `GrabaReg('delSavePreReg20', <id>)`.
2. `GrabaReg` envía el formulario a `POST delSavePreReg20?<sesión>&HTMLCveEvento=<id>&HTMLSaveDelReg=0`.

Liberar un lugar (`DelReg`) manda **la misma petición** que el paso 2: SIASE decide si registra o libera según si ya estabas. Por eso `nexuscli` revisa tu historial antes de cualquiera de las dos cosas. No pre-registra si ya estás en el evento o si ya no hay cupo, no libera si no estás o si tu asistencia ya se registró, y al terminar vuelve a leer el historial para confirmar el resultado.

El cuerpo de los dos pasos es el formulario completo, como lo envía el navegador: los campos ocultos (`HTMLCveEvento01`, `HTMLCveArea01`, `HTMLCveMes01`, `HTMLEc_Inscripcion`, `HTMLTrund`, `HTMLResill`, `HTMLFecha_Cita`...), el valor elegido de cada `select` y el checkbox marcado (`Evento[]=<id>`), codificado en ISO-8859-1.

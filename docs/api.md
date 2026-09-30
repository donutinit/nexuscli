# el API de Nexus

Lo que usa `nexuscli`, sacado del frontend de [plataformanexus.uanl.mx](https://plataformanexus.uanl.mx) (`main.js` y sus chunks `N.js`, un Angular 7). No es documentación oficial y puede cambiar sin aviso.

Las lecturas de esta página están probadas contra Nexus. Las escrituras copian campo por campo lo que manda el frontend y `tests/test_payloads.py` las fija, pero todavía no se han probado contra el servidor real.

## lo básico

El frontend lee su configuración de `/assets/js/config.js`. Ahí están el API (`https://api.nexus.uanl.mx/WebApi/`) y la base de los documentos (`https://plataformanexus.uanl.mx`).

Todas las operaciones son `POST https://api.nexus.uanl.mx/WebApi/<Dominio>/<Método>` con un cuerpo JSON y estos headers:

| header | valor |
| --- | --- |
| `Token` | el token de la sesión |
| `AreaAcademicaId` | el de la sesión (por ejemplo `56`) |
| `RolId` | `5` para estudiante, `2` para profesor |
| `SistemaId` | `1` |
| `Content-Type` | `application/json` |

Las respuestas son JSON y casi todas traen `"Sesion": {"Token", "Tiempo": {"Restante", "Sistema"}}`, donde `Restante` son los segundos que le quedan a la sesión. Los errores llegan con HTTP 200 y esta forma:

```json
{"Code": 1003, "ExceptionType": 3, "Message": "El rol no tiene permitido realizar esta acción."}
```

| código | significado |
| --- | --- |
| `2004` | el token expiró |
| `2011` | la sesión no existe: alguien entró con la misma cuenta desde otro lado |
| `1003` | el rol no tiene permiso para ese método |
| `1001` | "No se pudo realizar esta operación" |
| `31003` | tema de foro por equipo y la cuenta no está en ningún equipo |

Nexus admite una sola sesión por usuario. Entrar desde cualquier lado invalida el token anterior, que a partir de ahí responde `2011`.

Las fechas vienen en hora local de Monterrey y sin zona (`2026-10-12T23:59:00`). `0001-01-01T00:00:00` quiere decir vacío.

## entrar

La web entra desde SIASE, y esto se puede hacer sin navegador:

1. `GET https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/login.htm`. El formulario trae dos campos ocultos, `HTMLToken` y `HTMLPrograma`.
2. `POST https://deimos.dgi.uanl.mx/cgi-bin/wspd_cgi.sh/eselcarrera.htm` con esos campos más `HTMLTipCve=01` (alumno), `HTMLUsuCve` (matrícula) y `HTMLPassword`. La página que regresa arma con JavaScript la liga del botón "Ingresar" de Nexus:
   ```
   https://plataformanexus.uanl.mx/#/LoginSIASE?Usu=0x...&Ctrl=...&HTMLUsuario=<matrícula>&HTMLTipCve=01
   ```
3. `POST Seguridad/CrearSesionSIASE` con cuerpo `{}` y, en lugar del token, estos headers: `Control` (el valor de `Ctrl` decodificado, con los espacios cambiados por `+`), `ClienteIp: 0.0.0.0`, `Usuario` (`Usu`), `UsuarioClave` (`HTMLUsuario`) y `TipoClave` (`HTMLTipCve`). Responde `{"Sesion": {"Token", "AreaAcademicaId", "RolId", "Tiempo"}}`.
4. `POST Seguridad/ConsultarPerfil` con `{}` da la persona y su `CuentaId`, que se usa al mandar mensajes.

`Seguridad/FinalizarSesion` con `{}` cierra la sesión.

## leer

| método | cuerpo | regresa |
| --- | --- | --- |
| `Curso/ConsultarCarpetaCursos` | `{"CarpetaId": 0, "Pagina": 1, "Paginacion": 10}` | `Carpetas[].Cursos[]`: `CursoId`, `Nombre`, `Profesores`, `FechaFin`, `Bienvenida`, `Compromiso`, `Foro`. Con `Paginacion: 0` regresa todas. Solo salen las materias activas. |
| `Curso/ConsultarDetalleCurso` | `{"CursoId"}` | `Curso` con `Foro.ForoId`, `Modalidad`, `Compromiso` y `Profesores` |
| `Estructura/ConsultarEstructura` | `{"CursoId"}` | `Estructura.Etapas[].Evidencias[]` (fechas, `EnEquipo`, `EntregaExtemporanea`, `EntregarDocumentos`, `EntregarRecursoExterno`) y `ProductoIntegrador` |
| `Estructura/ConsultarDetalleEvidencia` | `{"EvidenciaId", "CursoId"}` | `Evidencia.Contenidos[]` (`Titulo`, `Descripcion` en HTML) y el tema de foro vinculado |
| `Estructura/ConsultarDetalleProductoIntegrador` | `{"CursoId", "ProductoIntegradorId"}` | `ProductoIntegrador`, con la misma forma |
| `Portafolio/ConsultarPortafolio` | `{"CursoId"}` | `ElementosEvaluables[]`: cada tarea con `Calificacion` (`Valor` de 0 a 100 y los `CriterioNivelDominioId` que marcó el profesor), `Entregas` y `Retroalimentaciones` |
| `Tarea/ConsultarTareas` | `{"CursoId": 0}` | las tareas de todas las materias, sin estado de entrega |
| `Tarea/ConsultarEntregas` | `{"CursoId", "ElementoId", "TipoElementoId"}` | `Entregas[]` de una tarea |
| `Equipo/ConsultarEquipoEstudiante` | `{"CursoId"}` | `Equipos[]` con `EquipoId`, `Nombre` y `Estudiantes` |
| `Equipo/ConsultarArchivosCarpetas` | `{"EquipoId", "CarpetaId": 0, "ElementoId", "TipoElementoId"}` | la carpeta del equipo para esa tarea |
| `Equipo/ConsultarRecursosExternos` | `{"EquipoId", "ElementoId", "TipoElementoId"}` | las ligas guardadas por el equipo |
| `Recurso/ConsultarRecursos` | `{"CursoId"}` y, opcionales, `"ElementoId"` y `"TipoElementoId"` | `Recursos` con `RecursoArchivos`, `RecursosExternos`, `RecursosWeb`, `RecursosLibros`, `RecursosArticulos`, `RecursosTextos`, `RecursosHTML` y `RecursoScorm`. Con `ElementoId` solo regresa los de esa tarea (su pestaña Recursos). |
| `Rubrica/ConsultarRubrica` | `{"TipoElementoId", "ElementoId"}` | `Rubrica` con `Criterios`, `NivelDominios` y `CriterioNivelDominios` (`Puntos`, `Descripcion`) |
| `ProgramaAnalitico/ConsultarProgramaAnalitico` | `{"CursoId"}` | `ProgramaAnalitico` con `Archivo.Documento`, `RepresentaionGrafica` (así, con la errata) y `MapaConceptual` |
| `Aviso/ConsultarAvisos` | `{"CursoId", "Asignados": true}` | `Avisos[]` |
| `Foro/ConsultarTemas/` | `{"ForoId"}` | `Temas[]` |
| `Foro/ConsultarComentarios/` | `{"CursoId", "TemaId"}` | `Tema.Comentarios[]`, con las respuestas anidadas en `Respuestas` |
| `Mensaje/ConsultarConversaciones/` | `{"CursoId"}` | `Conversaciones[]` |
| `Mensaje/ConsultarConversacionMensaje` | `{"ConversacionId"}` | la conversación y sus mensajes |

Los documentos (entregas, recursos, programas) se bajan con `GET https://plataformanexus.uanl.mx/<Documento.URL>`. La URL es relativa y trae espacios (`Contenedores F/Contenedor_7470/...pdf`), así que hay que codificarla. No pide token.

## escribir

Las subidas son `multipart/form-data` con los headers de autenticación más `DocumentoId: 0`. Los campos van en este orden, como los arma el frontend con `FormData`, y todos los valores son texto: `true` y `false` en minúsculas, y `null` como la palabra `null`.

### entregar un archivo a tu nombre

`Tarea/ActualizarEntregaDocumento`:

| campo | valor |
| --- | --- |
| `Documento` | el archivo |
| `EntregaId` | `0` |
| `TipoElementoId` | `1` actividad, `2` PIA |
| `ElementoId` | el id de la tarea |
| `EnEquipo` | `false` |
| `Estado` | `true` |
| `NombreDocumento` | el nombre del archivo |
| `CursoId` | la materia |

### entregar por el equipo

Son dos pasos, igual que "Entregar > En equipo" en la web:

1. `Equipo/ActualizarEquipoArchivo` con los mismos campos, `EnEquipo: true`, y al final `EquipoId` y `CarpetaId: 0`. Sube el archivo a la carpeta del equipo y regresa `Archivo.DocumentoId`.
2. `Tarea/VincularEntregaEquipo`, ya en JSON:
   ```json
   {"EquipoId": 7003, "EntregaId": 0, "CursoId": 100001, "ElementoId": 45, "TipoElementoId": 1,
    "TareaRecursoId": 5551, "Estado": true, "TipoEntrega": 1}
   ```
   donde `TareaRecursoId` es el `DocumentoId` del paso 1.

### entregar una liga

`Tarea/ActualizarEntregaRecursoExterno`:

```json
{"CursoId": 100001,
 "Entrega": {"EntregaId": 0, "TipoElementoId": 1, "ElementoId": 45, "Estado": true},
 "RecursoExterno": {"ExternoId": 0, "Entregado": false, "Estado": true,
                    "TipoRecursoExternoId": 2, "Titulo": "Video final", "Contenido": "https://..."},
 "EnEquipo": false, "EquipoId": 0}
```

`TipoRecursoExternoId` es `1` para embed y `2` para URL. En equipo, `EnEquipo` va en `true` con el `EquipoId`, y después se llama `VincularEntregaEquipo` con `TareaRecursoId` igual a `Entrega.RecursoExterno.ExternoId` y `TipoEntrega: 2`.

### borrar entregas

Un documento se borra con el mismo `Tarea/ActualizarEntregaDocumento`, sin archivo: `Documento`, `NombreDocumento` y `DocumentoId` en `null`, luego `CursoId`, `EntregaId` (el de la entrega), `TipoElementoId`, `ElementoId`, `EnEquipo` (el de la entrega) y `Estado: 0`.

Una liga se borra con `Tarea/ActualizarEntregaRecursoExterno`, con `Entrega.Estado` y `RecursoExterno.Estado` en `false`.

El archivo que queda en la carpeta del equipo se borra aparte con `Equipo/EliminarEquipoArchivo` y `{"EquipoArchivo": {"DocumentoId", "EquipoId"}}`.

### foro, mensajes y réplicas

| método | cuerpo |
| --- | --- |
| `Foro/ActualizarTemaComentario/` | `{"TemaComentario": {"TemaComentarioId": 0, "TemaId", "ComentarioPadreId": 0, "Comentario", "EstadoComentarioId": 1, "EsRetroalimentacion": false, "Estado": true, "ComentariosHijos": [], "Respuestas": []}}`. Para responder, `ComentarioPadreId` es el comentario original. |
| `Mensaje/ActualizarMensajeConversacion` | `{"MensajeConversacion": {"Mensaje", "MensajeConversacionId": 0, "ConversacionId", "EmisorCuentaId", "Estado": true}}` |
| `Mensaje/ActualizarConversacion` | `{"Conversacion": {"IntegranteConversacion": [{"IntegranteConversacionId": 0, "CuentaId", "RolId", "Estado": true}], "ConversacionId": 0, "EnviarCorreo": false, "Estado": true, "CursoId", "EsGrupo": false, "Nombre"}}` crea una conversación nueva |
| `Retroalimentacion/ActualizarComentarioRetroalimentacion` | `{"CursoId", "RetroalimentacionId", "ReplicaId": 0, "Comentario", "Estado": true}`, solo si el comentario tiene `DerechoReplica` |

## valores que se repiten

| campo | valores |
| --- | --- |
| `TipoElementoId` | `1` actividad o evidencia, `2` producto integrador (PIA) |
| `TipoEntrega` | `1` documento, `2` recurso externo |
| `RolId` | `5` estudiante, `2` profesor |

El número que la web enseña para cada actividad (`2.4`) es `Etapa.Posicion` + `.` + `Evidencia.Posicion`.

## actualizar esta referencia

Los servicios del frontend tienen la forma `XService.prototype.Metodo = function (...) { return this.API.POST(this.Dominio, 'Metodo', {...}) }`. Para encontrarlos, baja `main.js` y los chunks que carga de forma diferida (`0.js`, `1.js`, ..., más `common.js`), que están en la raíz del sitio, y busca `this.API.POST(` y `REQUEST_UPLOAD(`. Los componentes que arman los cuerpos están cerca del servicio que los llama; por ejemplo, las entregas están en `estructura-elemento-entrega-dialog` y en `components/equipo/documento`.

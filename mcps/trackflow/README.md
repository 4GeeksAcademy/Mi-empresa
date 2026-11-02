# TrackFlow MCP: servidor y cliente FastMCP

Servidor independiente bajo `mcps/`, con excepcion de arquitectura autorizada.
Reutiliza Incidents Manager e inventario por HTTP; no sustituye sus servicios,
su persistencia, validaciones ni transiciones. Los contratos de incidencias se
importan del backend; el DTO de productos y `Warehouse` se comparten sin ORM.

## Alcance de la entrega

- Servidor FastMCP y cliente FastMCP de discovery/llamadas.
- Streamable HTTP para multiples clientes remotos, no stdio. Toda peticion al
  transporte MCP necesita OAuth, incluido initialize y tools/list.
- OAuth delegado a **MCP Auth (`mcpauth`)**, no al proveedor integrado de FastMCP.
- El agente consulta incidencias mediante `langchain-mcp-adapters`. El acceso
  HTTP directo ha sido eliminado, sin fallback al backend.

Ejecutar desde la raiz con el proyecto uv raiz (Python >=3.14). No se crea otro
entorno de paquetes para el servidor. Dependencias anadidas con `uv add fastmcp`
y `uv add mcpauth`; el lock raiz registra las versiones.
La migracion del agente incorpora `langchain-mcp-adapters`, LangGraph y su
checkpointer SQLite al entorno raiz para validar el flujo completo.
FastMCP se limita a `>=3,<4` y MCP SDK a `>=1.26,<2`: FastMCP 4/MCP 2 no son
compatibles con las importaciones de `langchain-mcp-adapters` 0.3.1.
Validado con FastMCP 3.4.11, MCP 1.30.0 y adapters 0.3.1.

## Proveedor OAuth y configuracion

Usar un proveedor OAuth 2.1/OIDC con discovery, JWKS y PKCE S256.
Registrar el MCP como recurso/API; su audiencia debe ser exactamente la URL
publica del endpoint `/mcp`. Registrar clientes y conceder solo los scopes que
necesiten. Obtener access tokens mediante los flujos autorizados del proveedor;
este servidor no emite tokens ni implementa login.

| Variable | Uso |
| --- | --- |
| `TRACKFLOW_MCP_ISSUER` | Obligatoria. Issuer exacto anunciado por OIDC discovery. |
| `TRACKFLOW_MCP_RESOURCE_URL` | Obligatoria. Audiencia y URL del MCP, terminada en `/mcp`. |
| `TRACKFLOW_MCP_BACKEND_URL` | Backend interno existente; default `http://localhost:8000`. |
| `TRACKFLOW_MCP_HOST` | Default `127.0.0.1`; usar `0.0.0.0` en Codespaces. |
| `TRACKFLOW_MCP_PORT` | Default `8001`. |
| `TRACKFLOW_MCP_ALLOWED_ORIGINS` | Lista JSON de origenes de navegador autorizados; default `[]`. Sin paths ni comodines. |
| `TRACKFLOW_MCP_URL` | URL `/mcp` que usa el cliente. |
| `TRACKFLOW_MCP_TOKEN` | Access token del cliente, suministrado por entorno; nunca como argumento CLI. |

Ejemplo **sin secretos** (sustituir dominios):

```bash
export TRACKFLOW_MCP_ISSUER='https://auth.example.com/oidc'
export TRACKFLOW_MCP_RESOURCE_URL='https://mcp.example.com/mcp'
export TRACKFLOW_MCP_BACKEND_URL='http://localhost:8000'
export TRACKFLOW_MCP_HOST='0.0.0.0'
uv run python -m mcps.trackflow.server
```

No se cargan archivos de entorno implicitamente. Variables ausentes, discovery
invalido, issuer inconsistente o ausencia de JWKS impiden arrancar; no hay modo
anonimo ni token de desarrollo por defecto. HTTPS obligatorio excepto loopback.
Mantener el backend privado: los GET y las rutas de incidencias existentes no
estan protegidos por el OAuth de este servidor.

MCP Auth valida firma asimetrica, issuer, audiencia y scope global `mcp:access`.
Ademas se exige `exp` vigente sin tolerancia para tokens caducados. El algoritmo
no se toma del cliente: se usa la allowlist asimetrica de MCP Auth.
Los tokens del cliente nunca se reenvian al backend. Inventario solo utiliza GET
y no recibe credenciales capaces de crear productos o movimientos.

### Protected Resource Metadata y discovery

Rutas publicas RFC 9728 (no contienen herramientas ni datos de negocio):

- `/.well-known/oauth-protected-resource/mcp`
- `/.well-known/oauth-protected-resource`

Anuncian recurso, authorization server, scopes y bearer por cabecera. Los
rechazos HTTP 401/403 incluyen `WWW-Authenticate` con `resource_metadata`.
La metadata del authorization server se consulta en el proveedor, no se suplanta
con metadata del recurso. Un proveedor sin dynamic client registration requiere
registro previo del cliente; MCP Auth lo advierte al arrancar.

## Herramientas y minimo privilegio

Todas requieren `mcp:access`, mas el scope indicado:

| Tool | Scope | Entrada |
| --- | --- | --- |
| `list_incidents` | `incidents:read` | `{"filters": {}}`; filtros opcionales `status`, `origin`, `branch`, `category`. |
| `get_incident` | `incidents:read` | `{"ticket_id": 1}`; entero positivo. |
| `create_incident` | `incidents:create` | `{"incident": {"title": "...", "description": "...", "category": "tracking", "origin": "internal", "branch": "zaragoza"}}`. |
| `update_incident_status` | `incidents:update` | `{"ticket_id": 1, "update": {"status": "in_progress"}}`. |
| `query_inventory` | `inventory:read` | `{}` o `{"product_id": 1, "operation": "read"}`. |

Discovery MCP ofrece descripcion, input/output schemas, annotations y
`required_scopes` por tool. Incidencias devuelve los campos originales;
inventario devuelve `id`, `name`, `sku`, `warehouse`, `current_stock`.

Los dominios reales son diferentes: incidencias usa sede `los-angeles`,
inventario usa almacen `los_angeles`; ambos soportan `zaragoza`.
Las categorias de incidencias son `logistica`, `tracking`, `devolucion`,
`facturacion`, `soporte`; origenes `customer`, `branch`, `internal`.

Estado: `open -> in_progress/discarded`, `in_progress -> resolved/discarded`;
`resolved` y `discarded` son terminales. El cambio usa exclusivamente
`PATCH /api/incidents/{id}/status` y deja la validacion al backend.
Crear una incidencia no es idempotente: no reintentar automaticamente.

### Inventario: denegacion explicita

La politica de tools rechaza `operation` distinta de `read`, incluso si el
token incorpora permisos adicionales. Tambien rechaza nombres de tools no
autorizados; el cliente HTTP interno impone una allowlist de metodos/rutas que
prohibe cualquier escritura de inventario antes de enviar peticiones.
No existe scope `inventory:write` ni credencial de escritura de inventario.
No se bloquea POST al transporte `/mcp`: ese POST es necesario para consultas
JSON-RPC y no representa una escritura de negocio.

## Cliente FastMCP

Suministrar el token por un mecanismo seguro de entorno. No imprimirlo,
versionarlo ni pegarlo en comandos. Con `TRACKFLOW_MCP_TOKEN` ya configurado:

```bash
export TRACKFLOW_MCP_URL='https://mcp.example.com/mcp'
uv run python -m mcps.trackflow.client
uv run python -m mcps.trackflow.client --tool list_incidents --arguments '{"filters": {}}'
uv run python -m mcps.trackflow.client --tool get_incident --arguments '{"ticket_id": 1}'
uv run python -m mcps.trackflow.client --tool query_inventory
uv run python -m mcps.trackflow.client --tool query_inventory --arguments '{"operation": "delete"}'
```

El ultimo comando debe fallar con `READ_ONLY_INVENTORY` y exit code 1.
Las llamadas son explicitas: el cliente no crea ni modifica nada al arrancar.
El token se obtiene externamente; esta CLI no implementa refresco automatico.
El agente carga tools usando `langchain-mcp-adapters`; limitar su
token a `mcp:access incidents:read`; no habilitar mutaciones por defecto.
Su limite total de cinco segundos incluye sesion, discovery y llamada; errores
de auth, scopes, protocolo o servicio terminan en el fallback existente, no en
peticiones HTTP directas. RAG/incidencias/ambos conservan su enrutamiento.

## Errores y auditoria

| Situacion | Resultado |
| --- | --- |
| Sin bearer | HTTP 401, `missing_auth_header`. |
| JWT invalido, caducado o sin `exp` | HTTP 401, `invalid_token`. |
| Issuer/audiencia incorrectos | HTTP 401, `invalid_issuer` / `invalid_audience`. |
| Falta `mcp:access` | HTTP 403, `missing_required_scopes`. |
| Falta scope de tool | MCP `isError=true`, `INSUFFICIENT_SCOPE`. |
| Escritura inventario | MCP `isError=true`, `READ_ONLY_INVENTORY`. |
| Tool desconocida/prohibida | MCP `isError=true`, `TOOL_NOT_ALLOWED`. |
| Entrada invalida o transicion rechazada | MCP `isError=true`, `VALIDATION_ERROR`. |
| Incidencia/producto ausente | MCP `isError=true`, `NOT_FOUND`. |
| Backend 401/403 | `BACKEND_AUTHENTICATION` / `BACKEND_AUTHORIZATION`. |
| Timeout/conexion/status inesperado/payload invalido | `BACKEND_TIMEOUT`, `BACKEND_UNAVAILABLE` o `INVALID_BACKEND_RESPONSE`. |

Errores de tool se expresan conforme a MCP, no convirtiendo todo JSON-RPC en
HTTP 4xx. No se devuelven errores brutos del backend. Cada invocacion registra
`tool_invocation` con `tool`, cliente autenticado y resultado success/error,
tambien en rechazos. No se registran tokens, argumentos ni documentos de negocio.

## Validacion y evidencia

Verificacion de esta fase, 2026-11-02:

- 16 tests existentes de inventario e incidencias: PASS, ejecutados en el
  contenedor del backend con el codigo fuente montado.
- Servidor HTTP y cliente FastMCP: arranque, metadata y discovery de cinco tools
  con esquemas de entrada/salida: PASS.
- Firma/JWKS local, token ausente/invalido/caducado/sin expiracion, issuer,
  audiencia y scopes: rechazos verificados. El emisor local solo sirve para
  comprobacion aislada; **no acredita un login OAuth con un proveedor real**.
- Lectura de incidencias e inventario mediante MCP contra backend real: PASS.
- Rechazos por permisos de tool, escritura de inventario, tool desconocida y
  entrada invalida; logs de tool/cliente/resultado: PASS.
- Las comprobaciones iniciales no modificaron registros reales.
- Comprobacion aislada adicional: creacion/consulta y PATCH de estado usan las
  rutas correctas; codigo `VALIDATION_ERROR`, denegacion de escritura aun con
  scope adicional y allowlist de backend verificados. CORS permite el origen
  configurado y rechaza otro. Esto no sustituye la aceptacion de mutaciones reales.
- Sintaxis/CLI y `git diff --check`: PASS. Se selecciono `.venv` raiz mediante
  la herramienta del editor, pero Pylance continua reportando
  `reportMissingImports`. Para el cierre se ejecuto Pyright independiente en
  un contenedor con FastMCP 3.4.11: **0 errores y 0 avisos** en los modulos MCP,
  cliente del agente y contratos compartidos. El diagnostico del editor no se
  considera resuelto; el acceso al interprete local esta restringido por politica.

- Migracion: 39 regresiones existentes PASS con el entorno uv raiz. Grafo
  compilado -> adapters -> MCP autenticado -> ticket real existente: PASS,
  con trace SQLite temporal. Sin camino HTTP directo en el agente.
- Aceptacion local de las cinco tools contra backend real: PASS. Se creo
  exclusivamente la incidencia tecnica ID 2, titulo
  `[MCP VALIDATION] Local acceptance 2026-11-02`, y se paso por
  `open -> in_progress -> resolved`. Transicion inversa rechazada; incidencias
  preexistentes intactas. El registro queda identificado para auditoria.
- Cliente FastMCP, metadata y rechazos sin token y con tokens
  invalidos/caducados o scope de tool insuficiente se comprobaron de nuevo con
  FastMCP 3 y MCP SDK 1. Los emisores efimeros locales se detuvieron.

La aceptacion posterior con Logto real y MCP Playground queda registrada en
el checklist siguiente. El token del usuario no se leyo ni se obtuvo desde
archivos de entorno. El servidor se arranco con issuer y recurso publicos;
el usuario obtuvo los tokens y ejecuto las comprobaciones externas.
No se acredita login interactivo PKCE ni renovacion automatica de tokens.

### Checklist de aceptacion

Actualizacion con proveedor real: el usuario obtuvo un access token de Logto
con `mcp:access incidents:read` y verifico discovery y listado de incidencias
por la URL publica. Captura del grafo en `.agent-data/mcp-logto-evals.json`;
evaluador ejecutado nuevamente: routing_tool y tool_fallback, 2/2 PASS.
El not_found es el caso negativo esperado. Esto acredita el flujo M2M real,
no una prueba interactiva Authorization Code + PKCE en Playground.

| Criterio | Evidencia actual |
| --- | --- |
| Servidor en mcps y discovery | PASS local HTTP, cinco tools con esquemas. |
| Sin token no lista/ejecuta | PASS, HTTP 401 en ambas operaciones. |
| Gestion real de incidencias y PATCH status | PASS, incidencia tecnica 2, ciclo de vida verificado. |
| Inventario solo lectura | PASS, consulta real y denegacion explicita antes del backend. |
| Descripciones y esquemas | PASS discovery FastMCP. |
| Errores diferenciados | PASS auth, scopes, validacion y transicion invalida. |
| Auditoria por tool/cliente/resultado | PASS comprobacion local de logs. |
| Agente exclusivamente via MCP | PASS flujo real y 39 regresiones de tools/grafo/evals. |
| OAuth con proveedor externo | PASS cliente M2M y grafo con Logto real; PKCE interactivo pendiente en Playground. |
| Playground con URL publica Codespaces | PASS capturas del usuario: discovery, cinco tools, ciclo QA 3 y rechazo explicito de escritura. |

Evidencia Playground del 2026-11-02: el cliente de lectura lista incidencias y
consulta ticket 1; inventario devuelve INSUFFICIENT_SCOPE. Con el cliente de
validacion, inventario no muestra error (Empty response); el backend confirma
HTTP 200 y lista vacia. La operacion delete devuelve READ_ONLY_INVENTORY.
Se crea ticket QA 3, se cambia open -> in_progress, se consulta y se cierra
resolved. Una consulta posterior al backend confirma su persistencia.
Estas capturas acreditan uso de access tokens por cabecera en Playground,
no un flujo interactivo Authorization Code + PKCE.

### MCP Playground desde Codespaces

1. Configurar proveedor, clientes y scopes; no usar el emisor efimero de pruebas.
2. Reenviar el puerto 8001 y ponerlo publico, manteniendo el backend privado.
3. Configurar `TRACKFLOW_MCP_RESOURCE_URL` con la URL publica reenviada + `/mcp`
   y registrar esa misma audiencia en el proveedor.
4. Si el navegador conecta directamente, autorizar exclusivamente su origen
   mediante `TRACKFLOW_MCP_ALLOWED_ORIGINS='["https://origen-del-playground.example"]'`.
5. Arrancar servidor y conectar Playground con URL publica, nunca localhost.
6. Verificar discovery y un flujo por tool. Crear una incidencia de validacion
   identificable y usar su ID para consulta y transicion `open -> in_progress`;
   no modificar incidencias operativas ajenas.
7. Probar sin token, caducado, scopes insuficientes, entrada invalida y
   `query_inventory` con `{"operation": "delete"}`.
8. Guardar evidencia sanitizada por criterio; no capturar bearer ni credenciales.

## Instalacion y verificacion de entrega

Servidor MCP y API se ejecutan en **entornos separados**. FastAPI 0.117.1 del
backend utiliza Starlette 0.48.0; no instalar FastMCP dentro de ese entorno.
El manifiesto y requirements de la API incluyen `sse-starlette>=3,<3.6` para
evitar que la nueva dependencia MCP fuerce una version incompatible de Starlette.

### Servidor MCP y cliente

Desde la raiz, con Python >=3.14:

```bash
uv sync --locked
uv pip check
# Configurar variables publicas de servidor y arrancar en una terminal:
uv run --locked python -m mcps.trackflow.server
# En otra terminal, con URL y token de lectura inyectados de forma segura:
uv run --locked python -m mcps.trackflow.client --tool list_incidents --arguments '{"filters": {}}'
```

No usar `--active` para instalar en un entorno distinto al del proyecto.
No poner el token en argumentos de proceso, archivos versionados o capturas.
Si se usa un archivo local ignorado, uv debe recibir explicitamente
`--env-file`; el programa no lo lee automaticamente.

### Backend: instalacion limpia comprobada

El lock de uv de la API esta restringido por la politica de la organizacion;
no se accedio ni se modifico. **No se afirma que `uv sync --locked` de la API
este actualizado**: requiere sincronizacion por un mantenedor autorizado.
La ruta de requirements existente se comprobo en un entorno vacio de Python
3.12, sin depender de paquetes de la imagen de recuperacion:

```bash
uv pip compile services/api/requirements.txt --python-version 3.12 \
  --output-file /tmp/trackflow-api-delivery-requirements.txt
uv venv --python 3.12 /tmp/trackflow-api-delivery
uv pip sync --python /tmp/trackflow-api-delivery/bin/python \
  /tmp/trackflow-api-delivery-requirements.txt
uv pip check --python /tmp/trackflow-api-delivery/bin/python
```

Resultado de cierre: 162 paquetes compatibles; **20 pruebas API PASS**
(inventario, incidencias y endpoint del agente), incluyendo los calculos de
stock de las pruebas existentes. No se crearon productos en datos operativos:
la consulta de inventario en Playground sigue acreditando una lista vacia.
El archivo compilado temporal fija esa resolucion concreta; no equivale al
lock de uv versionado ni garantiza que futuras resoluciones sean identicas.

### Comprobaciones focalizadas

```bash
uv run --locked python -m pytest \
  tests/pipelines/test_agent_external_tools.py \
  tests/pipelines/test_agent_graph.py tests/pipelines/test_agent_evals.py -q
uv run --locked python -m scripts.evaluate_agent_traces \
  .agent-data/mcp-logto-evals.json
git diff --check
```

Resultados finales: **39 pruebas de cliente/grafo/evals PASS**, **20 pruebas
API PASS en entorno vacio**, evaluacion real Logto **2/2 PASS**, Pyright
independiente **0 errores/0 avisos**. Los traces privados no se incluyen en Git;
para reproducir la captura se necesita obtener un token vigente y ejecutar
`python -m scripts.capture_incident_evals` con las variables MCP del cliente.

### Operacion y limites conocidos

- Los puertos o procesos de Codespaces pueden detenerse o volver a privados.
  Comprobar primero health de backend y metadata publica sin login GitHub.
- En esta sesion el backend de recuperacion es
  `mi-empresa-agent-backend-mcp-ready`, puerto solo loopback; el servidor MCP
  es otro proceso. El arranque ordinario requiere la configuracion existente
  de base de datos, telemetria y volumenes descrita en el README del backend.
- La configuracion del token debe inyectarse tambien al proceso/contenedor
  del agente HTTP; la captura CLI no configura automaticamente dicho proceso.
- Rotar tokens caducados y mantener separados los clientes agente/validacion.
  Client credentials esta validado; login interactivo PKCE y refresco automatico
  no se implementaron ni se presentan como evidencia ejecutada.
- Los incidentes 2 y 3 son registros QA resueltos, no incidencias operativas.
  No borrar ni incluir cambios de datos en una publicacion sin revisar su alcance.
- No se modificaron secretos, infraestructura ni workflows. No hay commit.

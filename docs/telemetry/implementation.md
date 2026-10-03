# TrackFlow: captura de telemetria

## Alcance aprobado

Fase temporal sin persistencia de eventos, Supabase, dashboards ni infraestructura de streaming. Se conserva el catalogo original: frontend para intencion/experiencia, backend para resultados definitivos. El desarrollador aprobo captura mixta, entrega sin durabilidad y umbral configurable inicial 10.

`runtime-rules.json` complementa el catalogo personalizado, que declara sanitizacion pero no enumera valores controlados ni rangos. Ambos validadores importan los mismos enums de dominio, codigos, rutas conocidas, version `1.0` y rangos de enteros seguros. SKU se normaliza a mayusculas y se restringe a identificadores tecnicos. El envelope acepta `requestId` como UUID; un header no UUID se reemplaza por uno generado en el backend. Se eliminan query/fragmentos, se normalizan IDs de ruta y rutas desconocidas se reducen a `/unknown`. No se agregan propiedades al catalogo.

## Receptor y productores

- `POST /telemetry/events` valida un envelope cerrado de ocho campos y allowlists; acepta `{"events": [...]}` con hasta 100 eventos y responde `200 {"received": N}`. Lotes invalidos devuelven 422 sin reflejar valores originales en el error de la aplicacion.
- El stub registra exclusivamente cantidad y tipos, sin envelopes, propiedades ni almacenamiento. Es de desarrollo, no un colector listo para internet: faltan autenticacion del productor, limites de bytes/rate y deduplicacion duradera.
- Los productores backend validan y acumulan eventos por peticion; entregan un lote al receptor comun en proceso al finalizar la respuesta. No hacen HTTP contra su propio endpoint.
- Ordenes y cambios de estado se capturan despues del commit/escritura. Latencia se mide hasta enviar el ultimo bloque ASGI. Una respuesta abortada tras enviar cabeceras no ofrece confirmacion terminal fiable.
- Los proxies Next propagan `X-Request-ID` y `X-Session-ID`; FastAPI devuelve el primero y lo incluye en el log de peticiones con ruta normalizada. El backend acepta solo UUID como correlacion; headers arbitrarios se sustituyen por UUID. Navegacion y errores independientes generan su propio request ID.
- Un intento PUT/PATCH/DELETE sobre la ruta de productos rechazada o un campo stock/current_stock extra emite `direct_stock_edit_rejected`; no se crea una ruta de escritura ni se modifica stock fuera de ordenes trazables.
- Si el navegador detecta localmente que el JWT vencio, solicita `/auth/me` una vez con ese token antes de retirarlo. FastAPI confirma expiracion y emite `session_expired`; no se atribuye un usuario sin verificarlo.
- El log de excepciones no escribe mensaje, stack ni ruta cruda: solo tipo, ruta normalizada y requestId UUID.

## Servicio del navegador

`lib/telemetry.ts` expone `track(eventType, properties)`. Los demas metodos solo gestionan transporte, identidad y ciclo de vida. Se rechazan productores backend desde el cliente. No se intercepta fetch global: negocio usa `correlatedFetch` y telemetria usa un transporte separado, evitando recursiones.

- UUID y timestamp UTC se generan al capturar y se conservan durante reintentos.
- Cola de hasta 200 eventos en memoria; lotes de hasta 20 cada 10 segundos o al alcanzar 20. Se conservan eventos nuevos durante el envio; no se envia dos veces concurrentemente el mismo lote. Al saturarse la cola se descartan eventos nuevos.
- Timeout de envio de 5 segundos. Tres reintentos adicionales al original con esperas de 1, 2 y 4 segundos, despues se descarta. Los fallos del colector no generan eventos sobre si mismos.
- `visibilitychange` hidden y `pagehide` usan sendBeacon. False conserva el lote; true solo confirma aceptacion por el navegador, no recepcion. No se duplica un lote con fetch en vuelo: puede perderse si este se cancela al cerrar. No hay entrega exactamente una vez ni buffer duradero.
- sessionStorage guarda solamente UUID de sesion e ID tecnico del actor, no perfiles ni eventos. El UUID se conserva al recargar y rota al cambiar de actor/logout. El actor se obtiene de `/auth/me`; la vista autenticada espera esa verificacion. Si falla, no se inventa identidad.
- Vistas identicas: deduplicacion de 10 segundos por sesion/ruta. Filtros de proveedores: debounce de 500 ms. Errores globales: deduplicacion por codigo/ruta/release durante 60 segundos, maximo 20/minuto. Un ErrorBoundary cubre tambien errores de render React. Nunca se capturan mensajes ni stacks.
- Abandono: despues de editar un formulario, dejarlo/ocultarlo y transcurrir 60 segundos sin completarlo. Volver cancela el timeout; una solicitud en vuelo no se considera abandonada. Flujos: entrada, salida, alta de proveedor y alta de incidencia. No se puede emitir despues de destruir la pestana ni se infiere abandono de una simple vista.

## Configuracion

| Variable | Lugar | Uso |
| --- | --- | --- |
| `NEXT_PUBLIC_TELEMETRY_ENDPOINT` | Backoffice, build/arranque | Default `/api/telemetry/events`, proxy same-origin; permite receptor directo |
| `TELEMETRY_ENDPOINT` | Next servidor | URL receptor; fallback `${INCIDENTS_API_INTERNAL_URL}/telemetry/events` |
| `TELEMETRY_ENDPOINT` | FastAPI | Leida como configuracion; default `http://localhost:8000/telemetry/events`, sin redirigir el stub |
| `TELEMETRY_STOCK_THRESHOLD` | FastAPI | Entero positivo, default 10; invalido usa 10 |

Arranque local del backoffice:

```bash
cd uis/backoffice
NEXT_PUBLIC_TELEMETRY_ENDPOINT=/api/telemetry/events TELEMETRY_ENDPOINT=http://127.0.0.1:8000/telemetry/events INCIDENTS_API_INTERNAL_URL=http://127.0.0.1:8000 INVENTORY_API_INTERNAL_URL=http://127.0.0.1:8000 npm run dev -- --port 3001
```

Arrancar la API como indica su README, con la configuracion de negocio/auth existente. No se modificaron `.env.local`, secretos ni rutas protegidas. Docker incluye/monta el contrato readonly en `/docs/telemetry`; los builds usan contexto raiz. El proxy evita CORS para telemetria; no se cambiaron las reglas CORS existentes.

## Cobertura por evento

| Evento | Estado | Productor y punto |
| --- | --- | --- |
| `inbound_order_created` | Implementado, mandatory | Backend, commit de entrada |
| `outbound_order_created` | Implementado, mandatory | Backend, commit de salida |
| `direct_stock_edit_rejected` | Implementado, mandatory | Backend, payload con stock/current_stock y metodos de escritura rechazados en ruta de producto; sin crear ruta directa |
| `inventory_validation_failed` | Implementado, mandatory | Backend, 422 de inventario, SKU duplicado, producto ausente o stock insuficiente |
| `stock_threshold_triggered` | Implementado, mandatory | Backend, salida que cruza de stock >= umbral a < umbral, nunca al consultar |
| `login_succeeded` | Implementado, mandatory | Backend, credenciales/cuenta activa verificadas |
| `login_failed` | Implementado, mandatory | Backend, credenciales incorrectas o cuenta inactiva; actor anonimo |
| `session_expired` | Implementado, mandatory | Backend, JWT con firma valida vencido, incluso cuando el cliente lo detecta al cargar |
| `backoffice_section_viewed` | Implementado, mandatory | Frontend, seccion visible, tras verificar identidad si hay token |
| `workflow_abandoned` | Implementado, mandatory | Frontend, timeout de formulario iniciado y dejado sin completar |
| `api_latency_recorded` | Implementado, mandatory | Backend, respuesta terminada; errores completos y una muestra exitosa por ruta/sesion cada 10 s |
| `api_error_recorded` | Implementado, mandatory | Backend, 4xx/5xx, excluyendo receptor |
| `inventory_product_viewed` | Bloqueado | No hay pagina que renderice detalle; el selector de una orden no se presenta como vista de detalle |
| `outbound_order_rejected` | Implementado | Backend, producto ausente o stock insuficiente |
| `product_created` | Implementado | Backend, producto confirmado |
| `unauthorized_access_rejected` | Implementado | Backend, dependencia admin rechaza rol |
| `password_reset_requested` | Implementado | Backend, respuesta generica creada, sin revelar existencia de cuenta |
| `search_executed` | Implementado | Frontend, filtros de proveedores tras debounce y resultado recibido |
| `frontend_error_captured` | Implementado | Frontend, ErrorBoundary, window error y unhandledrejection, codigos controlados |
| `integration_call_failed` | Pendiente | Sin adaptador de integracion con politica de reintentos terminal instrumentable; no se inventa fallo logistico |
| `incident_created` | Implementado | Backend, alta confirmada por repositorio |
| `incident_status_changed` | Implementado | Backend, transicion confirmada, ambos estados conocidos |
| `supplier_status_changed` | Implementado | Backend, estado confirmado, ambos estados y pais conocidos |
| `report_exported` | Implementado | Backend, CSV generado listo para descarga |

El cruce backend <10 corresponde al aprobado; se conserva la alerta visual preexistente <=10. SKU antiguos fuera del formato tecnico se descartan de telemetria, sin alterar datos de productos.

## Verificacion y pendientes

```bash
cd services/api
python -m pytest -q
cd ../../uis/backoffice
npm ci
npm test -- --runInBand
npm run lint
npm run build
```

Pruebas de envelope, allowlists, privacidad/requestId, logs sanitizados, temporizador, lotes, cola durante envio, reintentos/IDs, beacon, deduplicacion, actor/sesion, expiracion auth, ErrorBoundary, abandono/reanudacion, 500, exclusion del receptor, ordenes, PATCH rechazado y cruce de umbral.

Verificado en Chromium mediante captura de requests: login y navegacion a inventario; dos lotes reales frontend -> proxy Next -> FastAPI con 200, envelope de ocho campos, actor autenticado, requestId UUID y ausencia de email/contrasena sinteticos. La respuesta `received` coincide con los eventos recibidos.

Pendientes fuera de esta fase: buffer/DLQ, deduplicacion duradera, retencion/RBAC, agregados batch, percentiles p95/p99 y muestreo consciente de p99, proteccion de login por IP anonimizada con agregacion tras el limite. No se captura IP ni se inventan propiedades para contadores. Web Vitals no se incluye sin aprobar contrato.

Docker: `.env` local de desarrollo creado desde valores no productivos; `docker compose config --quiet` y `docker compose build` pasan. El backend esta healthy, `/health` responde desde el host en puerto alternativo 8001, el backoffice responde 200 en puerto alternativo 3002 y `POST /telemetry/events` directo responde `{"received":0}`. Se usan puertos alternativos porque los procesos locales ocupan 3001/8000.

Pendiente de esta verificacion: desde `interfaces`, `http://backend:8000/health` resuelve pero termina en `UND_ERR_CONNECT_TIMEOUT`; `host.docker.internal` devuelve `EAI_AGAIN`. En auditoria, el POST desde el proxy del contenedor respondio 502 por esa limitacion, mientras que el flujo E2E en Chromium con UI y API ejecutados en host respondio 200. `.env` esta excluido por `.gitignore` y no contiene credenciales externas; su clave JWT es solo para desarrollo. Playwright y las bibliotecas Chromium se usaron temporalmente y se retiraron/restauraron sin cambiar manifests. La instalacion npm del lockfile informa 9 vulnerabilidades (8 altas y 1 critica), pendientes de evaluacion separada; no se actualizaron dependencias declaradas.
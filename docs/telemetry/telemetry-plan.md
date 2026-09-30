# Plan de Telemetría — TrackFlow

**Estado:** diseño para revisión | **Versión:** 1.0 | **Fecha:** 2026-09-22

## 1. Resumen ejecutivo

TrackFlow necesita convertir sus operaciones binacionales (Los Ángeles y Zaragoza) en información accionable sin modificar la regla de negocio existente: el stock solo cambia mediante órdenes de entrada o salida trazables a un usuario. Este plan propone un catálogo de eventos para inventario, autenticación, navegación, rendimiento, errores, incidencias y proveedores. Cada evento tiene una hipótesis y una decisión asociada; los eventos críticos se entregan en stream y los analíticos en batch.

El catálogo distingue requisitos **mandatory** (las métricas y controles pedidos por el RFI/contexto) de **opportunity** (instrumentación adicional propuesta). `event-schemas.json` contiene el contrato de envelope y el catálogo validable.

## 2. Alcance y fuentes

Este documento diseña telemetría, no la implementa. Se revisaron `CONTEXT.md`, `company-choice.md`, la memoria del proyecto, `services/api`, sus modelos, rutas y tests, y la documentación de `docs`, `services` y `uis`. El código actual implementa FastAPI con `/inventory`, `/auth`, `/api/incidents`, `/suppliers`, usuarios y perfiles; no se inventa telemetría de módulos que aún no tienen endpoint productivo.

## 3. Contexto, entidades y restricciones

- **Empresa:** TrackFlow, logística de última milla y almacenes en Estados Unidos y España.
- **Almacenes:** `los_angeles` y `zaragoza` (enum `Warehouse`).
- **Inventario:** `Product` identificado por `id`, `sku` y `warehouse`; el mismo SKU puede existir en ambos almacenes.
- **Movimientos:** `InboundOrder` y `OutboundOrder`, con `product_id`, `quantity`, `created_at` y `user_uuid`.
- **Autenticación:** usuarios con `id`, `email`, `role` (`admin`, `manager`, `user`) e `is_active`; JWT bearer y recuperación de contraseña.
- **Incidencias implementadas:** categorías `logistica`, `tracking`, `devolucion`, `facturacion`, `soporte`; estados `open`, `in_progress`, `resolved`, `discarded`; orígenes `customer`, `branch`, `internal`; sedes `los-angeles`, `zaragoza`, `central`.
- **Proveedores implementados:** país `US`/`ES`, categorías `transporte`, `embalaje`, `almacenaje`, `devoluciones`, `tecnologia`, estado `activo`/`suspendido`.
- **Restricción innegociable:** no se captura ni se propone un evento que represente una escritura directa de stock válida. Se registra el intento rechazado para seguridad/auditoría, y las escrituras válidas se atribuyen al usuario.
- **PII:** email, teléfono, dirección, contraseñas, tokens y texto libre no forman parte de los payloads operativos.

## 4. Principios de diseño

1. Un evento existe solo si responde a una hipótesis y habilita una decisión.
2. El backend es la fuente de verdad para órdenes, stock, autenticación y resultados; el frontend aporta intención y experiencia.
3. `event_type` usa `entidad_accion`, verbos en pasado y vocabulario estable.
4. Allowlist cerrada: `properties` solo contiene las claves declaradas para ese evento.
5. Los eventos son inmutables, versionados, idempotentes y correlacionables.
6. Se minimiza PII y se evita registrar secretos, cuerpos completos o texto libre.

## 5. Event Envelope

Todo evento se emite como `{ eventId, timestamp, sessionId, userId, event_type, schemaVersion, requestId, properties }`.

| Campo | Tipo/formato | Obligatorio | Regla |
|---|---|---:|---|
| `eventId` | UUID | Sí | Generado en el productor; deduplica reintentos. |
| `timestamp` | string ISO 8601 UTC | Sí | Momento de ocurrencia, no de ingestión. |
| `sessionId` | string o `null` | Sí | UUID de sesión; `null` en procesos sin sesión humana. |
| `userId` | string o `null` | Sí | ID interno (`user_uuid`/id de usuario), nunca email; `null` si anónimo. |
| `event_type` | string `entidad_accion` | Sí | Debe existir en el catálogo. |
| `schemaVersion` | semver mayor-menor | Sí | Inicialmente `1.0`; cambio incompatible incrementa major. |
| `requestId` | string | Sí | Se propaga frontend → API → logs; generado si falta. |
| `properties` | objeto cerrado | Sí | Solo allowlist; sin datos adicionales. |

Un evento sin autenticación conserva `sessionId` y usa `userId: null`. Los workers usan `sessionId: null` y `userId: null` salvo que exista un actor de servicio autorizado. `requestId` y `eventId` no son PII.

## 6. Taxonomía y catálogo

La frase justificativa de cada evento se expresa en las columnas **Hipótesis → decisión**. `mandatory` cubre el RFI, la trazabilidad mínima y salud operacional necesaria; `opportunity` amplía la exploración.

| event_type | categoría | clase | entrega | Hipótesis → decisión |
|---|---|---|---|---|
| `inbound_order_created` | inventory | mandatory | stream | Las entradas diarias reflejan reposición real → operaciones concilia recepción y stock. |
| `outbound_order_created` | inventory | mandatory | stream | El volumen de salidas y su distribución por almacén cambia la capacidad → se planifica picking y transporte. |
| `direct_stock_edit_rejected` | inventory | mandatory | stream | Alguien intenta saltarse la trazabilidad → seguridad corrige permisos y operaciones investiga. |
| `inventory_validation_failed` | inventory | mandatory | batch | Productos/SKU generan errores repetidos → se corrigen datos y UX. |
| `stock_threshold_triggered` | inventory | mandatory | stream | Un producto cae bajo el umbral → compras y operaciones reponen antes de una ruptura. |
| `inventory_product_viewed` | inventory | opportunity | batch | La demanda de consulta concentra ciertos SKU/almacenes → se priorizan vistas y reposición. |
| `outbound_order_rejected` | inventory | opportunity | stream | El stock insuficiente bloquea salidas → se reasigna inventario o se alerta al operador. |
| `product_created` | inventory | opportunity | batch | Se crean particiones de SKU de forma coherente → se audita el catálogo. |
| `login_succeeded` | authentication | mandatory | batch | La adopción y distribución de accesos es conocida → se dimensionan sesiones y soporte. |
| `login_failed` | authentication | mandatory | stream | Aumentan fallos de credenciales → seguridad activa protección; nunca se registra la contraseña. |
| `session_expired` | authentication | mandatory | batch | Expiraciones interrumpen operaciones → se ajusta UX o expiración segura. |
| `unauthorized_access_rejected` | authentication | opportunity | stream | Hay intentos de acceso a recursos no permitidos → se investigan permisos o abuso. |
| `password_reset_requested` | authentication | opportunity | batch | Se acumulan recuperaciones → se mejora acceso y soporte sin revelar existencia de usuario. |
| `backoffice_section_viewed` | navigation | mandatory | batch | Algunas secciones son más usadas → se priorizan mejoras. |
| `workflow_abandoned` | navigation | mandatory | batch | Un flujo iniciado no termina → se elimina fricción o se contacta al equipo. |
| `search_executed` | navigation | opportunity | batch | Las búsquedas muestran necesidades de descubrimiento → se mejoran filtros e índices. |
| `api_latency_recorded` | performance | mandatory | batch | La latencia se degrada por ruta/almacén → se optimiza antes de afectar operaciones. |
| `api_error_recorded` | errors | mandatory | stream | Suben 4xx/5xx → se prioriza respuesta y corrección. |
| `frontend_error_captured` | errors | opportunity | stream | Errores JS rompen flujos aunque la API esté sana → se corrige la interfaz. |
| `integration_call_failed` | performance | opportunity | stream | Una dependencia logística falla → se activa fallback o escalado. |
| `incident_created` | incidents | opportunity | batch | Categorías/orígenes muestran problemas operativos recurrentes → se asignan responsables. |
| `incident_status_changed` | incidents | opportunity | batch | Incidencias se estancan en un estado → se revisan SLA y carga. |
| `supplier_status_changed` | suppliers | opportunity | batch | Proveedores suspendidos afectan capacidad → compras busca alternativa. |
| `report_exported` | incidents | opportunity | batch | Los informes se exportan con frecuencia → se automatiza la distribución. |

### Propiedades y allowlists resumidas

El archivo JSON es la fuente normativa de tipos, propiedades, productor y momento de emisión. Para evitar ambigüedad, estas son las reglas comunes: `warehouse` solo `los_angeles|zaragoza`; `direction` solo `inbound|outbound`; `role` solo `admin|manager|user`; IDs y SKU son identificadores técnicos, no texto libre; `error_code` es una clase controlada; `route` es una ruta normalizada sin query string. En cada entrada del JSON, `properties` y `allowlist` deben contener exactamente los mismos nombres.

Los 12 eventos obligatorios son `inbound_order_created`, `outbound_order_created`, `inventory_validation_failed`, `direct_stock_edit_rejected`, `stock_threshold_triggered`, `login_succeeded`, `login_failed`, `session_expired`, `backoffice_section_viewed`, `workflow_abandoned`, `api_latency_recorded` y `api_error_recorded`. Se incluyen `login_succeeded` y `session_expired` como mandatory porque permiten medir accesos legítimos e interrupciones de sesión junto a los controles de seguridad; el resto del catálogo está marcado como oportunidad.

## 7. Estrategia stream vs batch

- **Stream:** movimientos de stock, rechazos de salida, intento de edición directa, umbral, login fallido, acceso no autorizado, errores API/frontend e integración. Requieren alerta o investigación rápida; objetivo de ingestión: ≤60 segundos.
- **Batch:** vistas, búsquedas, expiraciones, recuperaciones, incidencias, proveedores, exportaciones y latencia agregada. Se agregan cada 15 minutos para operación y diariamente para informes; no requieren reacción segundo a segundo.
- `api_latency_recorded` puede generarse como observación individual, pero su decisión se basa en ventanas agregadas de 5 minutos; el canal recomendado es batch.
- Cada evento del JSON incluye además `producer`, `source_layer` y `emit_when`: los eventos de resultado de negocio se emiten desde backend después del resultado definitivo (y después del commit cuando corresponda); los eventos de intención, navegación y errores de interfaz se emiten desde frontend en el momento indicado. Esto evita duplicar confirmaciones entre UI y API.
- Particionar por fecha, `event_type` y almacén cuando exista. Mantener al menos orden por `requestId` y deduplicar por `eventId`.
- Reintentar con backoff; no bloquear una operación de negocio por la caída del colector. Los eventos críticos deben tener buffer duradero y DLQ.

## 8. Throttle, debounce y deduplicación

- API: un evento por request; no reintentar emisiones sin conservar `eventId`.
- Navegación: debounce de 500 ms para cambios de filtro y máximo una vista idéntica por sesión/ruta cada 10 segundos.
- Latencia: muestrear 100% de errores y p99; máximo una observación exitosa por ruta y ventana de 10 segundos por sesión.
- Frontend: deduplicar por hash de `error_code + route + release` durante 60 segundos por sesión; límite de 20 eventos/minuto.
- Login fallido: conservar todos los eventos hasta un límite de seguridad de 10/minuto por IP anonimizada; después agregar un contador sin IP.
- Umbrales y órdenes nunca se muestrean: son trazabilidad operacional.

## 9. Privacidad, retención y gobernanza

Nunca capturar contraseñas, JWT, tokens de recuperación, secretos, tarjetas, headers de autorización, bodies completos, direcciones completas, email, teléfono, descripción completa de incidencia, contenido de mensajes o stack traces con valores sensibles. Los mensajes se reducen a códigos controlados; emails e IP se hashean con salt y rotación documentada; el `userId` interno se restringe por RBAC y se pseudonimiza para analítica; SKU y IDs operativos se conservan porque son necesarios para decisiones de inventario.

Retención recomendada: stream de seguridad/errores 90 días; eventos operativos 13 meses; agregados batch 24 meses. Acceso de mínimo privilegio para operaciones, seguridad y datos; auditoría de consultas. Separar el almacén de telemetría del de producción y cifrar tránsito/reposo.

## 10. Riesgos y exclusiones

Se descartan por ahora `shipment_delivered`, `carrier_assigned`, `return_approved` y métricas de CX porque CONTEXT los identifica como necesidades futuras, pero no hay entidades/endpoints implementados en esta copia. Se dejan como backlog de contrato, no como eventos emitibles hoy. También se excluyen grabaciones de pantalla, tracking de cada tecla, payloads libres y métricas de negocio no definidas: coste, riesgo de privacidad o falta de decisión clara.

Riesgos: eventos frontend/backend duplicados; pérdida durante caída del colector; relojes desalineados; falta de `requestId` en clientes antiguos; cardinalidad alta por SKU/ruta; y que un evento obligatorio se confunda con un log. Mitigaciones: generación server-side, sincronización NTP, validación del catálogo en CI, DLQ, límites de cardinalidad, contratos versionados y correlación por request.

## 11. Recomendaciones de implementación futura

1. Crear un productor común que valide envelope y allowlist antes de publicar.
2. Emitir eventos de inventario y autenticación en backend, tras conocer resultado y actor.
3. Propagar `requestId` desde UI y añadirlo a logs FastAPI.
4. Emitir frontend solo para intención/navegación/errores; no duplicar confirmaciones backend.
5. Añadir umbral configurable y evento de transición (no evento repetido por cada consulta).
6. Crear dashboards de salidas diarias, validaciones por SKU, rechazos de stock, fallos de login, alertas y latencia p95/p99.

### Contrato mínimo de implementación

Antes de publicar un evento, el productor debe validar que:

1. `event_type` existe una sola vez en `event-schemas.json`.
2. El envelope contiene los ocho campos requeridos y ningún campo adicional.
3. `properties` solo contiene nombres de su `allowlist` y contiene todas las propiedades marcadas como `required`.
4. La emisión respeta `producer`, `source_layer` y `emit_when` del catálogo.
5. El evento conserva el mismo `eventId` durante reintentos y propaga `requestId` entre frontend, API y logs.
6. Los valores se validan contra `allowed_values`, rangos numéricos y reglas de sanitización antes de salir del proceso productor.
7. No se publica la operación de negocio como confirmada hasta que el resultado descrito en `emit_when` se haya producido.

## 12. Checklist de aceptación

- [x] Envelope con los ocho campos requeridos.
- [x] Catálogo amplio, con más de cinco puntos de inventario.
- [x] Métricas obligatorias y oportunidades separadas.
- [x] Más de ocho eventos adicionales y siete categorías.
- [x] Hipótesis y decisión por evento.
- [x] Allowlist, PII y estrategia de entrega por evento en JSON.
- [x] Riesgos, exclusiones y throttling documentados.
- [x] Sin código de instrumentación.

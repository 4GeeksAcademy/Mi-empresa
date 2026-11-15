# Aislamiento multi-tenant: política y primer vertical slice

**Estado:** requisito y política confirmados por el propietario del producto. Hay un primer vertical slice implementado para autorización de RFP en rutas síncronas; no equivale a aislamiento completo del producto ni cubre todavía workers, almacenamiento/descargas, provisión de membresía ni otros dominios. Este documento evita que owner-scoping existente se presente como aislamiento integral entre empresas.

**Avance de auditoría:** se añadieron `Tenant`/`TenantMembership`, migración SQL, resolución server-side y filtros/autorización tenant en los endpoints RFP probados. La suite focalizada `services/api/tests/test_rfp.py` pasó (24 tests); la suite completa API dio 157 passed, 1 skipped y 1 fallo de timing no relacionado (`test_post_only_enqueues_identifier_under_200ms`: 680 ms frente al umbral de 200 ms). Se probaron canarios A/B, `tenant_id` de query manipulado, legacy sin tenant, tenant_member read-only, denegación sin membresía y acceso global platform `admin`/`manager`. Falta ampliar a trabajadores asíncronos, documentos/archivos, y operaciones de provisioning antes de declarar aislamiento integral o producción lista. No se asignarán registros legacy por inferencia.

## Evidencia del estado actual

- `services/api/auth_models.py`, `auth_db.py` y `routes/users.py`: identidad de usuario en TinyDB sin `tenant_id` ni membresía. El registro es público, no asigna empresa y rechaza campos extra. No se debe aceptar un tenant elegido en el payload público.
- `services/api/routes/rfp.py`: tenant users se resuelven desde `TenantMembership` persistida; el listado se filtra por tenant, el detalle y operaciones de ticket hacen autorización de recurso y legacy `tenant_id=NULL` es invisible a tenants. `admin`/`manager` conservan deliberadamente el acceso global RFP aprobado. Los workers todavía reciben principalmente `ticket_id` y su revalidación tenant no se ha completado.
- `services/task_store.py`: trabajos CSV/exportación se filtran por propietario. Es por usuario, no tenant. La entrada CSV tiene un máximo local de 10 MiB.
- `services/api/incidents/repository.py` y endpoints incidentes: datos y caché globales; las rutas operativas son staff-gated, pero no tenant-scoped.
- `services/api/database.py` (`SupplierRepository`): catálogo TinyDB global; caché por filtros no incluye tenant.
- `services/api/models.py` y `routes/inventory.py`: productos y órdenes SQLModel no contienen tenant; se consultan globalmente. Las órdenes guardan `user_uuid`, pero eso no constituye partición empresarial.
- `services/support_agent/chat.py`: `client_id` se obtiene de `user["client_id"]` si existe, o se deriva del ID de usuario. Auth persistente no define ese campo; fixture de chat lo inyecta. No es membresía autoritativa.
- `services/support_agent/memory.py` y `traces.py`: datos owner-scoped por ID de usuario.
- `services/knowledge/pipeline.py`: recuperación Qdrant valida `company == "trackflow"`, pero consulta globalmente sin filtro de tenant.

## Regla de seguridad acordada

- Objetivo: aislamiento estricto entre empresas en cualquier recurso que se clasifique tenant-owned.
- Resolver el tenant desde una membresía persistida y validada server-side; nunca confiar en `tenant_id`/`client_id` aportado por el cliente como autoridad.
- No inferir la empresa por dominio de correo electrónico.
- Las operaciones sin tenant válido deben fallar cerradas para recursos tenant-owned.
- Mantener explícitamente separadas las identidades de plataforma (admin/manager) y membresías de cliente. Decisión explícita del propietario: se conserva el acceso global que las rutas RFP actuales conceden a `admin`/`manager`, también al introducir el aislamiento tenant; no se redefine como acceso de `tenant_admin`/`tenant_member` ni como acceso excepcional de soporte. Esta capacidad de plataforma debe quedar claramente identificada y cubierta por pruebas, no confundirse con la membresía del cliente.
- No asignar en masa datos legacy a un cliente supuesto. La migración debe dejar los registros sin asociación en estado no visible a tenants hasta clasificación y aprobación del propietario del dato.

## Clasificación y política aprobadas (2026-11-15)

| Dominio | Clasificación aprobada | Reglas de acceso aprobadas |
|---|---|---|
| RFP / documentos, archivos y respuestas | Privados por empresa (tenant-scoped), sin enlaces públicos para usuarios tenant. | `tenant_admin` y `tenant_member` leen solo RFP de su empresa; solo `tenant_admin` crea/edita y puede borrar lógicamente, mientras `tenant_member` es de solo lectura. Se conserva el acceso global actual de los roles de plataforma `admin`/`manager` en las rutas RFP. Archivos, respuestas, descargas y exportaciones siguen el alcance de la RFP y la misma autorización; la retención del contenido borrado queda por definir antes de habilitar el borrado. |
| Invitaciones y membresías | Una cuenta pertenece a una empresa. | Admin de empresa puede iniciar invitaciones. El invitado puede aceptar/verificar correo, pero queda pendiente y sin tenant/acceso hasta aprobación y asignación por plataforma. Solo plataforma administra la membresía efectiva. |
| Incidentes | Globales de TrackFlow; no son privados por empresa. | Acceso exclusivo de personal de plataforma autorizado. Reportes/quejas privados de clientes, si se implementan, deberán ser recursos separados tenant-scoped y no reinterpretar este repositorio global. |
| CSV de incidentes y exports | Incidentes globales; cada export/job sigue privado por usuario propietario. | Usuarios tenant no acceden al repositorio global de incidencias. Los filtros de propietario de jobs/export siguen obligatorios y no equivalen a tenant isolation. |
| Productos, inventario y órdenes | Globales de TrackFlow. | Acceso exclusivo de personal de plataforma autorizado; los roles tenant no heredan permisos staff. Un futuro inventario de cliente deberá ser un dominio separado y tenant-scoped. |
| Proveedores | Catálogo global de TrackFlow. | Acceso exclusivo de personal de plataforma autorizado. Si se añaden proveedores propios de clientes, deberán separarse del catálogo global y aislarse por tenant. |
| Chat / sesiones WebSocket | Sesiones privadas por usuario. | No se comparten automáticamente dentro de la empresa. Los datos recuperados por el agente conservan los permisos de su fuente. |
| Memoria y trazas del agente | Privadas por usuario. | No visibles a otros miembros de la empresa salvo una función de compartir aprobada explícitamente. No inferir tenant de `client_id`; traces no deben exponerse por ID adivinable. |
| RAG / Qdrant | Corpus actual de TrackFlow global; documentos cargados por clientes tenant-scoped. | La credencial global MCP/RAG no consulta datos privados de tenants. Cualquier corpus de cliente debe usar filtro tenant obligatorio aplicado server-side. |
| Soporte de plataforma | Denegado por defecto para datos privados de tenant. | Excepción de hasta 4 horas, ligada a ticket/motivo y aprobación del cliente; debe expirar automáticamente y auditar operador, tenant, caso, aprobación, recursos y acciones. No habilita acceso general permanente. |
| Telemetría | Minimización de datos; no es mecanismo de autorización. | No agregar `tenant_id` salvo necesidad operativa aprobada; si se añade, restringir acceso y minimizar la información asociada. |

## Provisión, roles y límites aprobados

Decisiones del propietario del producto:

1. Una cuenta pertenece a una sola empresa.
2. El registro público no puede autoasignar tenant. Admin de empresa puede iniciar invitaciones, pero solo plataforma aprueba y asigna la membresía efectiva; hasta entonces la cuenta queda pendiente y sin acceso a recursos tenant.
3. Roles tenant mínimos: `tenant_admin` y `tenant_member`, distintos de los roles de plataforma `admin`/`manager`. `tenant_admin` puede leer, crear, editar y borrar RFP de su empresa; `tenant_member` solo puede leerlas. Ambos quedan excluidos de incidentes globales, inventario/órdenes y proveedores globales.
4. En RFP se conserva el acceso global actual de `admin`/`manager` como roles de plataforma, separado de las membresías tenant. Esto no concede acceso a roles tenant ni modifica los permisos sobre incidentes, inventario u otros dominios. El acceso excepcional de soporte a datos privados fuera de los permisos establecidos sigue denegado por defecto; la política futura de break-glass requiere máximo 4 horas, ticket/motivo, aprobación del cliente, expiración automática y auditoría detallada, y permanece deshabilitada hasta diseñar y verificar aprobación, auditoría inmutable y retención.
5. Los datos legacy sin asociación verificable se ponen en cuarentena y no son visibles a usuarios tenant hasta que plataforma los clasifique y asigne usando evidencia autoritativa. No inferir por propietario, correo, nombre ni contenido.
6. MCP sigue limitado a operaciones globales de TrackFlow; su credencial de servicio nunca accede a datos privados tenant.

## Diseño técnico y cobertura pendiente

- Entidad persistida `Tenant` y tabla de membresías; cuenta pública sin tenant hasta invitación/provisión.
- Contexto de tenant derivado de una membresía verificada al autenticar/autorizar. Revalidarlo en cada request y tareas asíncronas; no confiar solo en un JWT de larga duración si cambia la membresía.
- Añadir `tenant_id` no nulo a recursos tenant-owned y a claves únicas/índices. Aplicar la condición en cada query, mutación, export, descarga, cache key, telemetría y job. Usar consultas compuestas (`tenant_id` + recurso) y retornar 404 ante recurso de otro tenant.
- En Celery persistir tenant y actor autorizados en el job; el worker vuelve a validar pertenencia y aplica filtros. No derivar tenant del nombre de archivo o argumento libre.
- Aislar Qdrant con payload indexado `tenant_id` y filtro server-side; pruebas que insertan canarios en tenants A/B y verifican que cada uno recupera únicamente los suyos.
- Migraciones escalonadas: crear tablas/columnas nullable; clasificar/migrar con fuente fiable; bloquear acceso de tenant a registros no clasificados; verificar conteos/constraints; después imponer NOT NULL para las tablas tenant-owned.
- Cache keys incluyen tenant cuando datos tenant-scoped; invalidaciones y eventos también.
- Pruebas de seguridad: A/B no se ven mutuamente en listado, detalle, agregados, cambios, export/CSV/RFP, WebSocket, memoria/traces, RAG y accesos por IDs ajenos; ausencia de tenant falla cerrada; un tenant_id manipulado en request no cambia el alcance. Verificar además que `admin`/`manager` conservan el acceso global establecido para rutas RFP, sin que dicho permiso se propague a roles tenant ni a otros dominios.

## Flujos específicos aún bloqueados

1. Definir el mecanismo de invitación (token, expiración, reenvío y prevención de enumeración) y cómo validar que el correo verificado corresponde al invitado previsto.
2. Definir cuánto tiempo se retienen RFP/documentos tras el borrado lógico, quién puede restaurarlos y cómo operan backups/legal hold.
3. Especificar quién puede aprobar el acceso excepcional de soporte en nombre del cliente, cómo se acredita esa aprobación, y dónde se conserva la auditoría inmutable y por cuánto tiempo. Hasta diseñar e implementar ese mecanismo, el acceso excepcional debe permanecer deshabilitado (denegado por defecto).

La política funcional principal ya está aprobada y el slice HTTP síncrono RFP tiene cobertura inicial. No se debe afirmar que la aplicación sea multi-tenant segura de forma integral: primero completar workers, archivos/descargas y los demás dominios que puedan alojar datos tenant, y operar la provisión exclusivamente desde plataforma. Mantener fallo cerrado y registros no clasificados en cuarentena. Las preguntas restantes no cambian la política de acceso actual; bloquean invitaciones, borrado lógico y break-glass hasta tener reglas verificables.

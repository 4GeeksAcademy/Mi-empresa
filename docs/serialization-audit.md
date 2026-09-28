# Auditoría de serialización de la API

**Fecha:** 2026-09-21  
**Backend auditado:** `services/api`  
**Criterio:** `V` = serializado y adecuado, `A` = parcialmente serializado, `X` = sin contrato explícito.

## Alcance y metodología

Se revisaron los routers FastAPI, `main.py`, los modelos Pydantic y los repositorios de TinyDB/SQLModel. También se inspeccionaron los consumidores del backoffice para conservar los campos que realmente utiliza la UI. La auditoría distingue modelos de entrada, modelos de persistencia internos y modelos de respuesta.

## Resultado por endpoint

| Método | Ruta | Propósito | Estado inicial | Estado final | Payload de salida |
|---|---|---|---:|---:|---|
| GET | `/health` | Health check | X | V | `{status}` |
| POST | `/api/incidents` | Crear incidencia | V | V | Incidencia segura completa |
| GET | `/api/incidents` | Listar incidencias | V | V | Lista de `IncidentResponse` |
| GET | `/api/incidents/summary` | Métricas de incidencias | A | V | Totales y mapas agregados tipados |
| GET | `/api/incidents/{incident_id}` | Detalle de incidencia | V | V | `IncidentResponse` |
| PATCH | `/api/incidents/{incident_id}/status` | Cambiar estado | V | V | `IncidentResponse` |
| POST | `/api/incidents/analyze` | Analizar CSV | X | V | Nombre de archivo y resumen tipado |
| GET | `/api/incidents/results/export` | Descargar CSV | X | V* | `StreamingResponse` CSV, sin JSON aplicable |
| POST | `/suppliers` | Crear proveedor | V | V | `SupplierResponse` |
| GET | `/suppliers` | Listar proveedores | A | V | Proyección explícita de proveedor |
| GET | `/suppliers/{id}` | Detalle de proveedor | V | V | `SupplierResponse` |
| PATCH | `/suppliers/{id}/rate` | Actualizar tarifa | V | V | `SupplierResponse` |
| PATCH | `/suppliers/{id}/status` | Actualizar estado | V | V | `SupplierResponse` |
| DELETE | `/suppliers/{id}` | Eliminar proveedor | X | V | `SupplierDeleteResponse` |
| POST | `/auth/login` | Autenticar | V | V | Solo token y tipo bearer |
| GET | `/auth/me` | Usuario autenticado | V | V | Usuario, rol y perfil seguro |
| POST | `/auth/forgot-password` | Solicitar recuperación | V | V | Mensaje genérico anti-enumeración |
| POST | `/auth/reset-password` | Restablecer contraseña | V | V | Mensaje, sin token ni credenciales |
| POST | `/auth/change-password` | Cambiar contraseña | V | V | Mensaje, sin credenciales |
| POST | `/users` | Registro público | A | V | Respuesta mínima con id, rol, estado y fecha; no reenvía email ni `hashed_password` |
| GET | `/users` | Listar usuarios | V | V | Lista sin credenciales |
| GET | `/users/{id}` | Detalle de usuario | V | V | Usuario sin credenciales |
| PUT | `/users/{id}` | Actualizar usuario | V | V | Usuario sin credenciales |
| DELETE | `/users/{id}` | Eliminar usuario | V | V | Sin cuerpo, HTTP 204 |
| GET | `/profiles/me` | Ver perfil propio | V | V | Perfil del usuario |
| PUT | `/profiles/me` | Actualizar perfil propio | V | V | Perfil actualizado |
| GET | `/inventory/products` | Listar productos | V | V | Producto y stock calculado |
| POST | `/inventory/products` | Crear producto | V | V | Producto y stock inicial |
| GET | `/inventory/products/{id}` | Detalle de producto | V | V | Producto y stock calculado |
| POST | `/inventory/orders/inbound` | Registrar entrada | V | V | Orden aplanada |
| POST | `/inventory/orders/outbound` | Registrar salida | V | V | Orden aplanada |
| GET | `/inventory/orders` | Listar órdenes | V | V | Órdenes aplanadas |

## Decisiones de payload

- Los listados reutilizan una proyección segura solo cuando coincide con el detalle. No se incluyen relaciones SQLModel completas.
- Las órdenes de inventario devuelven `product_id`, nombre, SKU, cantidad, dirección y fecha. Se elimina `user_uuid`, que es un identificador interno server-side no utilizado por la UI.
- `/auth/login` devuelve exclusivamente `access_token` y `token_type`.
- `/users` utiliza `RegistrationResponse`, una proyección específica de registro que no devuelve el email enviado por el cliente.
- Las rutas de recuperación y cambio de contraseña devuelven un mensaje; nunca devuelven contraseña, hash o token.
- `/auth/me` conserva `email`, porque la vista de perfil lo consume, pero no expone ningún campo de credenciales.
- `/users` usa `UserResponse`, que excluye deliberadamente `hashed_password`.
- El análisis CSV tiene un esquema explícito para su nombre de archivo y resumen. La exportación es una descarga CSV, por lo que se documenta como respuesta binaria `StreamingResponse` y no como JSON.

## Entrada y límites de escritura

Los esquemas de entrada permanecen separados de los de respuesta. Los payloads de autenticación, usuarios, perfiles, proveedores e inventario rechazan campos desconocidos mediante `extra="forbid"`. Esto impide que el cliente envíe campos internos como `hashed_password`, `updated_at`, IDs o atributos no soportados.

## Sensibles excluidos

No se serializan `hashed_password`, contraseñas, tokens de recuperación, secretos ni `user_uuid` de las respuestas de inventario. Los repositorios pueden leer credenciales internamente para autenticar, pero esas estructuras no se retornan desde una ruta.

## Verificación completada

- `GET /health`
- `GET /api/incidents/summary`
- `GET /suppliers`

Resultados observados el 2026-09-21:

- `SECRET_KEY=test-secret-key-for-serialization python -m pytest -q` → **62 passed**, 36 warnings externos/deprecaciones.
- `docker compose up -d` → backend **Healthy** e interfaces **Running**.
- `GET /health` → HTTP 200, `{"status":"ok"}`.
- `GET /api/incidents/summary` → HTTP 200 con `total_incidents`, `by_status`, `by_category`, `by_origin` y `by_branch`.
- `GET /suppliers` → HTTP 200 con lista JSON.
- La inspección de esos tres payloads no encontró `hashed_password`, `password`, `access_token` ni `user_uuid`.
- `GET /openapi.json` → HTTP 200; todos los endpoints JSON muestran un esquema de respuesta y las descargas CSV/204 están justificadas como respuestas sin cuerpo JSON.

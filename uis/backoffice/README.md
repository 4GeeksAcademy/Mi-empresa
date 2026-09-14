# TrackFlow Backoffice

Aplicacion interna de operacion en Next.js + TypeScript.

## Objetivo
Mostrar una vista inicial de operaciones y CX con logica de negocio importada desde src (Hito 2), sin duplicar codigo.

## Integracion de logica
El modulo app importa funciones y datos desde:
- ../../src/types/models.ts
- ../../src/utils/*.ts

## Scripts
- npm run dev
- npm run build
- npm run lint

## Analizador de incidencias

- Ruta UI: `/incidents-analysis`
- Endpoint esperado:
	- `POST /api/incidents/analyze`
	- `GET /api/incidents/results/export`
- Configuracion de URL backend en frontend:
	- `NEXT_PUBLIC_INCIDENTS_API_URL` (por defecto `http://localhost:8000`)

## Directorio de proveedores

- Ruta UI: `/suppliers`
- Endpoints usados desde la UI:
	- `POST /suppliers`
	- `GET /suppliers?pais=&categoria=`
	- `GET /suppliers/{id}`
	- `PATCH /suppliers/{id}/rate`
	- `PATCH /suppliers/{id}/status`
	- `DELETE /suppliers/{id}`

## Gestión de inventario

- Variable de entorno del cliente: `NEXT_PUBLIC_INVENTORY_API_URL` (por defecto `/api/inventory`, proxy interno del backoffice)
- Variable opcional del servidor: `INVENTORY_API_INTERNAL_URL` (por defecto `http://127.0.0.1:8000`)
- Rutas UI:
	- `/backoffice/inventory/products`
	- `/backoffice/inventory/orders/inbound`
	- `/backoffice/inventory/orders/outbound`
	- `/backoffice/inventory/orders`
- La integración con la API está centralizada en `lib/inventory.ts` y envía el token JWT como `Authorization: Bearer <token>`.
- El frontend marca como stock bajo cualquier valor de `current_stock` menor o igual a 10 unidades. Es un umbral operativo de alerta visual; la API sigue siendo la fuente de verdad para impedir salidas superiores al stock real.

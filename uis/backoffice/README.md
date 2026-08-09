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

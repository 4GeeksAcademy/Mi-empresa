# Progress Log

## 2026-07-21

### Estado inicial
- Repo en formato plantilla con estructura base.
- Sin AGENTS.md en raiz.
- Sin carpeta .agents.
- Sin carpeta memory-bank.
- Sin apps uis/website y uis/backoffice.

### Objetivo de esta ejecucion
- Crear infraestructura de agentes completa y operativa.
- Inicializar website y backoffice en Next.js + TypeScript.
- Migrar Hito 1 a website.
- Integrar logica Hito 2 en backoffice por import directo.

### Riesgos identificados
- Importar codigo TypeScript desde fuera de la carpeta de app requiere configuracion de Next.
- Mantener consistencia visual sin romper separacion entre website y backoffice.

### Proximos pasos
1. Crear AGENTS.md y .agents.
2. Implementar website.
3. Implementar backoffice.
4. Validar build/lint.
5. Actualizar este log con resultados.

### Resultado de la ejecucion
- Infraestructura de agentes creada: memory-bank, AGENTS.md y .agents con reglas y skill verificable.
- uis/website creado en Next.js + TypeScript con landing completa y formulario de aplicacion.
- uis/backoffice creado en Next.js + TypeScript con dashboard operativo inicial.
- Integracion Hito 2 completada: imports directos desde src/types y src/utils sin copiar logica.

### Validaciones ejecutadas
- uis/website: npm run lint (ok), npm run build (ok).
- uis/backoffice: npm run lint (ok), npm run build (ok).

### Decision tecnica relevante
- En backoffice se usa webpack para dev/build porque Turbopack no resolvio imports externos del directorio src en este contexto. Se mantiene externalDir habilitado.

## 2026-08-15

### Objetivo de esta ejecucion
- Implementar Directorio de Proveedores end-to-end (FastAPI + TinyDB + Next.js backoffice) con seed idempotente y validaciones estrictas.

### Cambios implementados
- Backend en `services/api`:
	- Nuevos modelos Pydantic para proveedores en `models.py`.
	- Repositorio TinyDB en `database.py` con CRUD y filtros por pais/categoria.
	- Rutas REST en `routes/suppliers.py`:
		- `POST /suppliers`
		- `GET /suppliers`
		- `GET /suppliers/{id}`
		- `PATCH /suppliers/{id}/rate`
		- `PATCH /suppliers/{id}/status`
		- `DELETE /suppliers/{id}`
	- Integracion del router en `main.py` sin romper endpoints de incidencias.
	- Seeder idempotente en `seed.py`.
	- Test suite nueva en `tests/test_suppliers.py`.
- Frontend en `uis/backoffice`:
	- Nueva pagina `app/suppliers/page.tsx`.
	- Nuevo componente cliente `components/suppliers-directory.tsx` con:
		- listado de proveedores
		- filtros por pais/categoria sin recarga
		- alta de proveedor
		- actualizacion de tarifa
		- cambio de estado activo/suspendido
		- feedback de errores y exitos en UI
	- Nuevas rutas proxy Next en `app/api/suppliers/**` para conectar UI con backend.
	- Navegacion actualizada para acceso al directorio.

### Validaciones ejecutadas
- Backend:
	- `pytest -q` en `services/api` -> OK (`7 passed`).
	- `python seed.py` dos veces -> inserta en primera ejecucion y `0` en segunda (idempotencia OK).
- Frontend:
	- `npm run lint` en `uis/backoffice` -> OK.
	- `npm run build` en `uis/backoffice` -> OK.

### Decision tecnica relevante
- Como el contexto visible no incluye un contrato de proveedores formal en archivo, se centralizaron enums y campos de dominio en `services/api/models.py` para facilitar ajuste rapido si cambia el contexto evaluador (paises US/ES, estados activo/suspendido, categorias de producto y tarifa por kg).

### Riesgos y deuda tecnica
- Si el evaluador usa un contrato de categorias o nombre de campo de tarifa distinto, sera necesario ajustar constantes de dominio y seed.
- El flujo de CI deberia separar dependencias de runtime y test (actualmente `httpx` queda en `requirements.txt` para asegurar reproducibilidad local de pruebas).

## 2026-07-21 (nueva sesion)

### Objetivo de esta ejecucion
- Implementar Gestor de Incidencias Centralizado completo:
	1. Extraer validacion a paquete compartido `packages/shared/validators/`
	2. Crear backend CRUD de incidencias con TinyDB en `services/api/incidents/`
	3. Crear seed script para datos historicos CSV
	4. Crear componentes frontend en `uis/backoffice`: formulario, listado, resumen
	5. Actualizar navegacion y validar lint/build

### Cambios implementados

- **Paquete compartido de validacion** (`packages/shared/validators/`):
	- `incident_validator.py`: constantes (ALLOWED_CATEGORIES, ALLOWED_STATUSES, REQUIRED_FIELDS), funciones (normalize, normalize_key, parse_optional_score, validate_record), excepcion CsvFormatError.
	- `__init__.py`: re-exporta todo lo publico.

- **Backend de incidencias** (`services/api/incidents/`):
	- `models.py`: modelos Pydantic IncidentCreate, IncidentStatusUpdate, IncidentResponse, IncidentPersistence, IncidentFilters. Mapa de transiciones de estado VALID_STATUS_TRANSITIONS.
	- `repository.py`: IncidentRepository con TinyDB. Metodos: create, list (con filtros), get, update_status (valida transiciones), get_summary (agregaciones). Singleton.
	- `routes/incidents.py`: 5 endpoints REST (`POST /`, `GET /`, `GET /summary`, `GET /{id}`, `PATCH /{id}/status`) con manejo de errores 400/404/500.
	- `main.py`: router de incidencias registrado primero.
	- `pyproject.toml`: includes actualizado.
	- `analysis.py` y `__init__.py`: migrados a shared validators.

- **Seed script** (`scripts/seed_incidents.py`):
	- Lee CSV, transforma datos, usa validate_record. Idempotente via incident_ids. 70 insertados + 30 invalidos. Verificado.

- **Frontend** (`uis/backoffice/`):
	- `components/incident-form.tsx`: formulario con todos los campos, validacion cliente, feedback de errores por campo, spinner en submit.
	- `components/incidents-list.tsx`: listado con filtros (status/origin/branch), estados loading/error/empty/vacio, tarjetas con badge de estado, acciones de transicion con optimistic update.
	- `components/incidents-summary.tsx`: panel de metricas con graficos de barras por status/categoria/origen/sede + total general.
	- `app/incidents/page.tsx`: pagina de listado.
	- `app/incidents/new/page.tsx`: pagina de nuevo formulario.
	- `app/incidents/summary/page.tsx`: pagina de resumen.
	- `app/api/incidents/route.ts`, `[id]/route.ts`, `[id]/status/route.ts`, `summary/route.ts`: proxies al backend.
	- `app/layout.tsx`: navegacion actualizada con enlaces a Incidencias, Nueva incidencia, Resumen.

### Validaciones ejecutadas
- tests/test_analysis.py: 2/2 tests pasan.
- uis/backoffice: npm run lint (ok), npm run build (ok) — 15 rutas generadas correctamente.
- seed: 70 incidencias insertadas, segunda ejecucion 0 insertadas (idempotente).

### Proximos pasos (recomendados)
- Conectar seed con el CSV real de TrackFlow cuando este disponible.
- Implementar autenticacion/autorizacion en los endpoints de incidencias.
- Agregar paginacion en el listado de incidencias.
- Agregar tests para los nuevos endpoints de incidencias.
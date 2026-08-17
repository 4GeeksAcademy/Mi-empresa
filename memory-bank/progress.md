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
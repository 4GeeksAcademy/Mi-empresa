# TrackFlow Incidents API

Servicio backend para analizar ficheros CSV de incidencias y exportar metricas.

## Endpoints

- `POST /api/incidents/analyze`
  - Request: `multipart/form-data` con campo `file` (CSV)
  - Response: HTTP 202 con `{"task_id": "..."}`; el analisis se ejecuta en el worker
- `GET /tasks/{task_id}`
  - Response: `task_id`, estado (`pending`, `started`, `success`, `failure`) y resultado disponible
- `GET /api/incidents/results/export`
  - Response: descarga de `results.csv` del ultimo analisis
- `POST /suppliers`
  - Request: JSON con `nombre`, `pais`, `categorias_producto`, `tarifa_por_kg`, `status`
  - Response: proveedor creado con `id` y `updated_at`
- `GET /suppliers`
  - Query params opcionales: `pais`, `categoria`
  - Response: listado de proveedores
- `GET /suppliers/{id}`
  - Response: detalle de proveedor por id
- `PATCH /suppliers/{id}/rate`
  - Request: JSON con `tarifa_por_kg` (> 0)
  - Response: proveedor actualizado
- `PATCH /suppliers/{id}/status`
  - Request: JSON con `status` (`activo` o `suspendido`)
  - Response: proveedor actualizado
- `DELETE /suppliers/{id}`
  - Response: confirmacion de borrado

## Cola de tareas (DEV-55)

Redis es el broker y backend de resultados de Celery. API, worker y Flower leen
la misma `REDIS_URL`; Compose usa `redis://redis:6379/0`. Los CSV y resultados
se guardan en el volumen compartido `task_data`, y los fallos terminales en una
DLQ SQLite persistente. El mensaje de Celery contiene solo el `task_id`.

Desde la raiz del monorepo, iniciar y comprobar los servicios:

```bash
docker compose up -d redis backend worker flower
docker compose ps
docker compose exec redis redis-cli ping
```

La API escucha en `http://localhost:8000` y Flower en
`http://localhost:5555`. Detener o reanudar un proceso por separado:

```bash
docker compose stop backend     # el worker sigue procesando
docker compose start backend
docker compose stop worker      # la API sigue disponible
docker compose up -d worker
docker compose logs -f worker
```

El endpoint requiere un token Bearer valido. Define `TOKEN` con un JWT obtenido
por el flujo de autenticacion existente. Para demostrar una tarea completada y
otra fallida:

```bash
printf 'incident_id,category,status,satisfaction_score\nI-1,tracking,cerrado,5\n' > /tmp/dev55-ok.csv
curl -sS -H "Authorization: Bearer $TOKEN" -F file=@/tmp/dev55-ok.csv http://localhost:8000/api/incidents/analyze
```

La respuesta incluye `task_id`; consultar su estado y resultado con:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:8000/tasks/<task_id>
```

Para observar la DLQ tras tres fallos consecutivos (dos reintentos, con esperas
de 2 y 4 segundos), enviar un CSV con cabecera invalida:

```bash
printf 'wrong,header\n1,2\n' > /tmp/dev55-fail.csv
curl -sS -H "Authorization: Bearer $TOKEN" -F file=@/tmp/dev55-fail.csv http://localhost:8000/api/incidents/analyze
```

Flower muestra tareas encoladas, en ejecucion, completadas y fallidas en su
dashboard. Los logs del worker incluyen `task_id`, intento, estado, duracion y,
si falla, el error. El worker es un proceso Compose independiente de FastAPI.

## Run local

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=../.. uvicorn main:app --reload --port 8000
```

Desde la raiz del monorepo, la alternativa recomendada es `docker compose up`.
El servicio usa `DATABASE_URL` y `SECRET_KEY` del `.env` raiz; los valores de
`.env.example` son placeholders exclusivos para desarrollo.

## Tests

```bash
cd services/api
pytest -q
```

## Seed de proveedores

```bash
cd services/api
python seed.py
```

El seed es idempotente: no duplica proveedores existentes por `nombre + pais`.

## Reporting de negocio

El servicio `services/reporting/` expone el pipeline ejecutivo sin modificar el
reporte técnico:

- `GET /reporting/pipeline/status?run_id=<uuid>` devuelve la última ejecución
  o una ejecución concreta. Requiere autenticación.
- `POST /reporting/pipeline/runs` recibe `window_start`, `window_end` exclusivo
  y `country_codes`; encola el deployment Prefect y requiere rol admin.
- `GET /reporting/kpis?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` consulta las
  filas KPI de destino. `end_date` es exclusivo; admite filtros opcionales
  `country_code` y `metric_codes`.

La API requiere un deployment Prefect llamado
`trackflow_business_performance_flow/production` (configurable mediante
`TRACKFLOW_REPORTING_DEPLOYMENT`) y un worker activo para encolar ejecuciones.
El pipeline se puede ejecutar en local con `uv run --project services/api
python data/pipelines/pipeline.py`; su ventana por defecto es de siete días. El
diseño propone refresco cada cinco minutos, pero el schedule solo está activo
cuando se configura el deployment y su worker.

Los conectores de envíos, costes, devoluciones, CSAT y FX no están presentes.
Hasta que se conecten, el pipeline lee telemetría solo como señal de
reconciliación y no publica valores KPI ni ceros inferidos. `GET /telemetry/report`
y `services/telemetry/analysis.py` son independientes y permanecen intactos.

## Telemetria

`GET /telemetry/report` devuelve `events_per_day`, `error_rate_by_type` y
`latency_by_endpoint` para un período opcional (`start_date` inclusivo y
`end_date` exclusivo, ambos ISO 8601 con zona horaria). Sin parámetros usa los
últimos siete días hasta ahora. El informe se cachea en memoria durante 60
segundos por combinación de parámetros. La tasa de errores divide los eventos
`api_error_recorded` entre las observaciones `api_latency_recorded`; como las
latencias exitosas se muestrean, no representa la tasa total de fallos de
producción.

`POST /telemetry/events` acepta `{"events": [...]}` con hasta 100 elementos,
valida cada envelope y sus allowlists de forma independiente y responde
`200 {"received": N, "stored": M, "rejected": R}`. Los eventos validos se
guardan juntos en una sola transaccion en `telemetry_events`; los eventos del
backend usan el mismo receptor en proceso. El campo `service` se deriva del
productor declarado en el catalogo (`frontend` -> `backoffice`, `backend` ->
`api`). `eventId` se almacena como la PK UUID `id`; `tags` conserva `properties`
y el resto del envelope. La tabla tiene exactamente `id`, `timestamp`, `service`,
`event_type`, `level`, `value`, `message` y `tags`; `level` usa `info` y `value`
`message` son nulos mientras el envelope no defina esos campos.

La tabla se crea junto al esquema SQLModel al iniciar la API. Tiene indices por
`timestamp` y `event_type`, e indice GIN sobre `tags`; la API solo expone
insercion, no actualizacion ni borrado. Un error de persistencia revierte el lote
y responde HTTP 500; un envelope no parseable responde HTTP 422. Un `eventId`
repetido no crea una fila nueva y cuenta como `rejected`; `stored` solo cuenta
filas insertadas por primera vez. Antes de desplegar sobre una tabla existente,
ejecutar una vez `migrations/20261006_telemetry_event_contract.sql`, ya que
`create_all` no altera tablas creadas previamente. La migración conserva una
copia de reintentos idénticos por `eventId` y aborta si detecta copias divergentes.

Los productores backend persisten mediante el receptor comun en proceso y no
hacen HTTP contra `TELEMETRY_ENDPOINT`. `TELEMETRY_STOCK_THRESHOLD` configura
el cruce de stock bajo (default 10).
Consultar [cobertura y limitaciones](../../docs/telemetry/implementation.md).

## Script nocturno independiente (DEV-53)

Aplicar `migrations/20261019_job_runs.sql` antes de activar el job. Esta migracion
crea `job_runs` e indices, sin alterar `telemetry_events` ni `pipeline_runs`.
El script no se ejecuta dentro de FastAPI ni necesita levantar la API.
APScheduler se ejecuta en `scripts/nightly_scheduler.py`, en un proceso aparte
y sin hooks de FastAPI. El perfil Compose `scheduler` arranca solo ese servicio.
Consultar [operacion, scheduler y pruebas](../../scripts/README.md#dev-53-nightly-telemetry-export).
Los `requestId` recibidos se limitan a UUID; errores internos se registran con
ruta normalizada y tipo de excepción, sin mensaje ni stack.

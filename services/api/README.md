# TrackFlow Incidents API

Servicio backend para analizar ficheros CSV de incidencias y exportar metricas.

## Endpoints

- `POST /api/incidents/analyze`
  - Request: `multipart/form-data` con campo `file` (CSV)
  - Response: resumen JSON con metricas e invalidos por tipo
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

## Run local

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
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

## Telemetria

`POST /telemetry/events` acepta `{"events": [...]}` con hasta 100 elementos,
valida cada envelope y sus allowlists de forma independiente y responde
`200 {"received": N, "stored": M, "rejected": R}`. Los eventos validos se
guardan juntos en una sola transaccion en `telemetry_events`; los eventos del
backend usan el mismo receptor en proceso. El campo `service` se deriva del
productor declarado en el catalogo y `tags` conserva `properties`.

La tabla se crea junto al esquema SQLModel al iniciar la API. Tiene indices por
`timestamp` y `event_type`, e indice GIN sobre `tags`; la API solo expone
insercion, no actualizacion ni borrado. Un error de persistencia revierte el lote
y responde HTTP 500; un envelope no parseable responde HTTP 422.

Los productores backend persisten mediante el receptor comun en proceso y no
hacen HTTP contra `TELEMETRY_ENDPOINT`. `TELEMETRY_STOCK_THRESHOLD` configura
el cruce de stock bajo (default 10).
Consultar [cobertura y limitaciones](../../docs/telemetry/implementation.md).
Los `requestId` recibidos se limitan a UUID; errores internos se registran con
ruta normalizada y tipo de excepción, sin mensaje ni stack.

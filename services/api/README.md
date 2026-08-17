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

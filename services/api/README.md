# TrackFlow Incidents API

Servicio backend para analizar ficheros CSV de incidencias y exportar metricas.

## Endpoints

- `POST /api/incidents/analyze`
  - Request: `multipart/form-data` con campo `file` (CSV)
  - Response: resumen JSON con metricas e invalidos por tipo
- `GET /api/incidents/results/export`
  - Response: descarga de `results.csv` del ultimo analisis

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

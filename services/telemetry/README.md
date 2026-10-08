# Telemetría: análisis

`analysis.py` contiene agregaciones de solo lectura sobre `telemetry_events`:

- `events_per_day`: recuento por día UTC y `event_type`.
- `error_rate_by_type`: eventos `api_error_recorded` por `error_code` y día, divididos por los eventos observados `api_latency_recorded` de ese día. Como las latencias exitosas se muestrean, la tasa describe la muestra de telemetría y no la tasa total de fallos en producción.
- `latency_by_endpoint`: latencia media y tamaño de muestra por ruta normalizada y día UTC.

Cada consulta filtra el intervalo `[start_date, end_date)` y selecciona solo las
columnas necesarias. Las funciones no escriben datos ni resuelven ventanas por
defecto; el endpoint de la API prepara el intervalo y cachea el informe durante
60 segundos.
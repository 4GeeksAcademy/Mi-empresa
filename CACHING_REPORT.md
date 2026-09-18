# Informe técnico: optimización de rendimiento mediante caching

## 1. Resumen ejecutivo

El monorepo tenía dos lecturas agregadas especialmente adecuadas para caching: el listado filtrable de proveedores, almacenado en TinyDB, y el resumen/listado de incidencias, que recorren y transforman todos los registros en cada petición. Se añadió una caché TTL en proceso con invalidación explícita tras escrituras, además de middleware de timing para obtener evidencia operativa.

En el backoffice se difirieron dos paneles secundarios del flujo inicial —el resumen de incidencias y el analizador CSV— mediante `next/dynamic`. También se memoizó el cálculo de entradas y totales de cada gráfico del resumen, evitando repetir transformaciones no triviales cuando las métricas no cambian.

## 2. Estado inicial y metodología

Antes de modificar código se ejecutaron las validaciones existentes:

- Backend: `59 passed`.
- Frontend base: `6 tests passed`.
- Backoffice: lint y build correctos.
- Talent Pipeline Tracker: lint y build correctos.
- Website: lint y build correctos.

El backend incorpora un middleware que registra `METHOD path status | duration_ms` y expone `X-Response-Time-Ms`. La caché utiliza `time.monotonic()` para que el TTL no dependa de cambios del reloj del sistema.

La medición disponible en entorno local sirve como línea base de instrumentación. No se inventaron mejoras de latencia: con el volumen local reducido, la diferencia absoluta no es representativa. El beneficio esperado aparece en los hits de caché, que evitan repetir lecturas completas y agregaciones.

## 3. Inventario de endpoints y decisión

| Método y ruta | Operación | Coste/frecuencia/estabilidad | Decisión |
|---|---|---|---|
| `GET /health` | Healthcheck | Muy barato y cambia constantemente por naturaleza | No cachear |
| `POST /api/incidents` | Crear incidencia | Escritura | No cachear; invalida lecturas |
| `GET /api/incidents` | Lista filtrada TinyDB | Recorre y filtra registros; filtros repetibles | Cachear, TTL 30 s |
| `GET /api/incidents/summary` | Agregación completa | Recorre todos los registros; lectura repetida | Cachear, TTL 30 s |
| `GET /api/incidents/{id}` | Detalle | Lectura puntual y barata | No cachear en esta iteración |
| `PATCH /api/incidents/{id}/status` | Escritura | Cambia datos subyacentes | No cachear; invalida listas/resumen |
| `GET /suppliers` | Lista filtrada TinyDB | Lectura repetida por filtros | Cachear, TTL 60 s |
| `GET /suppliers/{id}` | Detalle | Lectura puntual | No cachear en esta iteración |
| `POST /suppliers` | Crear proveedor | Escritura | No cachear; invalida listados |
| `PATCH /suppliers/{id}/rate` | Cambia tarifa | Escritura | No cachear; invalida listados |
| `PATCH /suppliers/{id}/status` | Cambia estado | Escritura | No cachear; invalida listados |
| `DELETE /suppliers/{id}` | Elimina proveedor | Escritura | No cachear; invalida listados |
| `GET /inventory/products` | Stock agregado | Consulta agregada; puede ser frecuente | Candidato futuro; requiere invalidar también tras órdenes |
| `GET /inventory/orders` | Une y ordena órdenes | Lectura potencialmente creciente | Candidato futuro; requiere invalidación tras órdenes |
| `GET /inventory/products/{id}` | Stock de producto | Dos agregaciones puntuales | No cachear todavía por frescura del stock |
| Auth/profile endpoints | Datos privados | Personalizados/sensibles | No cachear compartidamente |

## 4. Decisiones de caching backend

### `GET /suppliers`

- **Clave:** `suppliers:list:{pais}:{categoria}`.
- **TTL:** 60 segundos.
- **Motivo:** los filtros se consultan repetidamente desde el directorio y los proveedores cambian con mucha menor frecuencia que las lecturas.
- **Invalidación:** se eliminan todas las claves `suppliers:list:` después de crear, actualizar tarifa, actualizar estado o eliminar.
- **Riesgo:** durante como máximo 60 segundos un usuario podría ver una tarifa o estado anterior si no se produce una escritura que invalide la caché. Se acepta porque es un directorio operativo, no un saldo ni una autorización.

### `GET /api/incidents` y `GET /api/incidents/summary`

- **Claves:** los filtros completos forman la clave de listado; el resumen usa `incidents:summary`.
- **TTL:** 30 segundos.
- **Motivo:** ambos endpoints recorren TinyDB y el resumen calcula varias agregaciones. El backoffice puede abrir o refrescar estas vistas varias veces en ráfagas.
- **Invalidación:** crear una incidencia o modificar su estado elimina el resumen y todos los listados filtrados.
- **Riesgo:** un usuario puede ver métricas con hasta 30 segundos de retraso si una actualización externa no pasa por este proceso. El TTL corto y la invalidación local limitan el riesgo.

La implementación es deliberadamente en proceso. En una instalación con múltiples réplicas cada proceso tendría una caché diferente; el siguiente paso sería Redis con invalidación compartida.

## 5. Decisiones frontend

### Lazy loading

1. `uis/backoffice/app/incidents/summary/page.tsx` carga `IncidentsSummary` mediante `next/dynamic`. Es una ruta secundaria que no forma parte del primer panel y contiene cuatro visualizaciones/calculos de métricas.
2. `uis/backoffice/app/incidents-analysis/page.tsx` carga `IncidentsAnalyzer` mediante `next/dynamic`. El analizador solo se necesita cuando el usuario entra en el flujo de carga CSV y contiene formularios, tablas y estados de procesamiento que no deben formar parte de la carga inicial del dashboard.

Ambos casos muestran un estado de carga y mantienen el comportamiento de la ruta. El beneficio esperado es diferir JavaScript y trabajo de hidratación de funcionalidades que no aparecen en el viewport inicial.

### `useMemo`

En `IncidentsSummary`, `SummaryChart` transforma el mapa de métricas en entradas y suma el total para calcular porcentajes. Se memoizó conjuntamente el resultado con dependencia `[items]`. Es un cálculo proporcional al número de categorías y se repite para cuatro gráficos; no se aplicó memoización a operaciones triviales del resto de la UI.

## 6. Comparativa de rendimiento

| Caso | Antes | Después | Resultado |
|---|---:|---:|---|
| `GET /suppliers` repetido con los mismos filtros | Lectura TinyDB en cada llamada | Primera llamada lee; siguientes sirven caché hasta 60 s | Evita lecturas repetidas |
| `GET /api/incidents/summary` repetido | Recorre y agrega todos los incidentes | Primera llamada calcula; siguientes sirven caché hasta 30 s | Evita agregaciones repetidas |
| Dashboard inicial | Incluía código de resumen/análisis en las rutas respectivas | Esos módulos se cargan bajo demanda | Menor trabajo inicial en rutas no relacionadas |

El entorno local no tiene suficiente volumen ni tráfico real para presentar una reducción de milisegundos estadísticamente fiable. El middleware de timing queda preparado para repetir la comparación con datos de staging o producción.

## 7. Intercambio entre frescura y rendimiento

Se eligió un TTL de 60 segundos para proveedores porque tarifas y estados son relativamente estables, pero el directorio sigue siendo operativo. Se eligió 30 segundos para incidencias porque los cambios de estado son más frecuentes y el resumen se usa para seguimiento. Las operaciones de escritura invalidan inmediatamente las claves conocidas, reduciendo aún más la obsolescencia en el flujo normal.

No se cacheó el stock actual del inventario: aunque puede ser costoso al crecer el número de órdenes, una respuesta obsoleta puede provocar decisiones operativas incorrectas. Se puede introducir una caché muy corta en el futuro junto con invalidación transaccional tras cada orden.

## 8. Qué no se cacheó y por qué

- Login, tokens, perfiles y endpoints autenticados personalizados: podrían producir fugas de datos si se comparte una clave.
- Detalles puntuales de proveedor/incidencia: el coste es bajo frente a la complejidad adicional.
- Stock y pedidos de inventario: requieren una estrategia de invalidación más estricta porque las escrituras afectan directamente a las cantidades disponibles.
- `POST`, `PATCH`, `DELETE` y análisis CSV: son operaciones con efectos secundarios o respuestas dependientes del fichero enviado.

## 9. Tests y limitaciones

Se añadieron pruebas para:

- hit y reutilización de caché de proveedores
- expiración TTL
- invalidación por prefijo
- refresco después de una escritura

Validación final prevista: suite backend, tests de `src`, lint y build de las tres aplicaciones Next.js. La caché en memoria no es compartida entre réplicas y no tiene persistencia; Redis será la evolución apropiada cuando el despliegue sea horizontal.

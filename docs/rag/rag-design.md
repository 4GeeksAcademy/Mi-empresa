# Diseño de la base de conocimiento RAG de TrackFlow

## Estado y alcance

Este documento describe la implementación del hito RAG para el asistente del equipo comercial. La integración y la validación end-to-end se ejecutaron el **2026-10-30** contra el endpoint de embeddings configurado, generación real y Qdrant local. El conjunto original de ocho consultas obtuvo Recall@3 **1.00**, por encima del criterio 0.80; tras ampliar el set a once preguntas durante esta auditoría, la evaluación real volvió a dar **1.00 (11/11)**. Es un resultado de este corpus/modelo y no una garantía sobre consultas futuras.

Fuentes de conocimiento, y solo ellas, bajo `docs/company-knowledge-base/`:

- `trackflow-sla-delivery.es.md`
- `trackflow-returns-policy.es.md`
- `trackflow-carrier-coverage.es.md`
- `trackflow-storage-pricing.es.md`

`trackflow-BRIEFING.es.md` define requisitos y vocabulario, pero no forma parte del corpus indexado. Las respuestas deben usar exclusivamente evidencia recuperada, identificar la fuente y sección, reconocer la falta de evidencia y evitar inferencias presentadas como hechos. Los documentos se tratan como datos, no como instrucciones.

## Arquitectura

1. `services/knowledge/indexing.py` transforma los cuatro Markdown en chunks y genera embeddings con la API compatible OpenAI configurada.
2. Cada vector se almacena en Qdrant, colección `trackflow_knowledge`, con distancia coseno y payload `{company, source_document, section, language, chunk_index, text}`.
3. `services/knowledge/pipeline.py` embebe la consulta, busca candidatos en Qdrant, filtra por score mínimo (predeterminado `0.35`) y entrega el contexto recuperado a un modelo de generación distinto del modelo de embeddings.
4. El modelo redacta la respuesta con citas de fuente/sección. Incluso cuando no hay contexto, la aplicación llama al modelo con contexto vacío e instrucción explícita de no inventar.
5. `POST /knowledge/query` en FastAPI exige el usuario autenticado. La UI Next.js de `/knowledge` utiliza un proxy que reenvía la autorización.

No se utiliza framework de orquestación RAG. Los clientes son Qdrant Client y OpenAI Python SDK con URLs compatibles configurables.

## Preparación del corpus e idempotencia

El parser de `markdown-it-py` mantiene bloques semánticos completos: párrafos y listas, con la jerarquía de encabezados en `section`. No se corta un párrafo por longitud ni se mezcla el briefing con las fuentes. La vista previa del corpus disponible produjo **14 chunks**: SLA 3, devoluciones 5, cobertura de transportistas 3 y almacenamiento 3. Los bloques medían entre 138 y 532 caracteres. La preservación del texto, el payload, el UUID5 determinista, la repetición sin duplicados y la limpieza de puntos obsoletos se probaron con embeddings simulados y Qdrant en memoria; esto no mide la calidad semántica de embeddings reales.

La dimensión se infiere del primer vector real. La colección debe usar esa misma dimensión y distancia coseno. Al reindexar, el proceso hace upsert de puntos actuales y solo después elimina puntos obsoletos; un fallo de upsert no desencadena la limpieza. El proceso de publicación no es atómico frente a lectores concurrentes, por lo que debe ejecutarse un solo indexador a la vez. Hay que reindexar al cambiar de modelo de embeddings, aunque la dimensión coincida.

## Decisiones de chunking y embeddings

El corpus es pequeño (cuatro documentos comerciales, 14 bloques semánticos en
la vista previa), así que se prioriza mantener evidencia autocontenida frente
a producir una cantidad uniforme de ventanas. Un bloque Markdown de párrafo o
lista se conserva entero: esto mantiene juntas condiciones como la ventana de
devolución y sus excepciones, y evita separar la introducción de una lista de
sus reglas. No se fuerza un límite artificial de tokens porque los bloques
observados son cortos (138–532 caracteres); si las fuentes crecen, habrá que
medir tamaños en tokens y subdividir únicamente bloques largos respetando
límites de oración y metadatos. No se añade overlap: headings jerárquicos en
`section` proporcionan contexto de procedencia sin duplicar pasajes vecinos en
resultados.

Se usa un modelo dedicado de embeddings, distinto del modelo generativo, para
representar tanto chunks como consultas en el mismo espacio vectorial. El
modelo se configura por entorno y no se codifica en el repo; dimensión 1024 fue
la observada en la ejecución real, pero se descubre dinámicamente para evitar
asumir una dimensión específica del proveedor. La distancia coseno se elige
porque compara la orientación semántica de vectores normalizados y corresponde
al score filtrado por `min_score=0.35`. Ese corte es conservador/provisional,
no calibrado con un conjunto de desarrollo independiente; debe reevaluarse si
cambia modelo o corpus. Las citas usan `source_document` y `section`, y los
embeddings no reemplazan la verificación de condiciones contractuales.

## Configuración

Se requieren estos nombres en el entorno (no guardar valores secretos en este documento):

- `RAG_EMBEDDING_BASE_URL`, `RAG_EMBEDDING_API_KEY`, `RAG_EMBEDDING_MODEL`
- `RAG_GENERATION_BASE_URL`, `RAG_GENERATION_API_KEY`, `RAG_GENERATION_MODEL`
- `QDRANT_URL` (por defecto `http://localhost:6333`) y opcionalmente `QDRANT_API_KEY`

Embeddings y generación deben usar modelos distintos y endpoints compatibles con sus respectivas operaciones de API. La dimensión observada en esta ejecución fue 1024. Compose incluye Qdrant local persistente (`qdrant/qdrant:v1.15.4`). Se fijó `qdrant-client>=1.15,<1.17` (resuelve 1.16.2) para mantener compatibilidad con el servidor.

## Ejecución y evaluación

Desde la raíz del repositorio, con dependencias instaladas y configuración disponible:

```bash
uv run python -m services.knowledge.indexing --preview
uv run --env-file .env python -m services.knowledge.indexing
uv run --env-file .env python scripts/evaluate_rag.py
```

El segundo comando escribe la colección dedicada; el tercero consulta Qdrant y calcula Recall@3 sobre las consultas de `data/eval/test-queries.json`. El conjunto tiene once consultas, con expected source y section y cobertura de los cuatro documentos, incluida una pregunta sobre Black Friday/Rebajas. El criterio del hito es Recall@3 ≥ 0.80. Ejecución real del 2026-10-30: **11 hits / 11 consultas = 1.00**, objetivo aprobado. El filtro de relevancia predeterminado `0.35` no se calibró con un conjunto separado y sigue siendo un parámetro que conviene monitorizar.

Qdrant se agregó al Compose de desarrollo (`docker compose up -d qdrant`). La comprobación de disponibilidad Python local debe ejecutarse dentro del entorno del proyecto (`uv run ...`) o desde el contenedor API; el Python global puede no incluir `qdrant-client`.

## Validaciones ejecutadas

- Vista previa real de corpus: 14 chunks con distribución indicada arriba.
- Pruebas de indexador con mocks y Qdrant en memoria: OK.
- `uv run python -m pytest tests/pipelines/test_rag.py -q`: 6 passed (incluye prueba de generación con contexto vacío).
- `uv run --project services/api --extra test pytest services/api/tests/test_knowledge.py -q`: 2 passed (con aviso de deprecación de dependencia).
- `docker compose config --quiet`: OK.
- Backoffice: `npm run lint -- --no-warn-ignored`: OK; `npm test -- --runInBand`: 4 suites, 15 tests passed.
- Las seis variables de configuración estaban presentes en el entorno cargado desde el `.env` raíz; sus valores no se imprimieron. Una prueba previa obtuvo HTTP 403, pero el reintento del 2026-10-30 respondió correctamente con vector de 1024 dimensiones.
- Indexación real en `trackflow_knowledge`: 14 chunks, dimensión 1024. Qdrant local accesible desde el entorno del proyecto.
- Evaluación real de retrieval tras ampliar el set: Recall@3 1.00 (11/11; criterio >=0.80).
- Consulta real sobre devoluciones internacionales generó una respuesta en español citando `returns-policy | Política de Devoluciones`, mantuvo el requisito de gestión manual y recomendó confirmar condiciones específicas no documentadas.
- El cliente Qdrant se fijó a la rama compatible `>=1.15,<1.17` para evitar la advertencia de compatibilidad con el servidor 1.15.4.

## Bloqueos y pendientes

1. Mantener operativo el acceso al endpoint de embeddings; puede fallar temporalmente (hubo un 403 antes de la prueba exitosa).
2. Repetir la evaluación en el entorno objetivo al cambiar corpus, modelo de embeddings o proveedor. Esta evaluación abarca once casos y no representa toda la distribución de consultas.
3. Revisar periódicamente respuestas, especialmente las salvedades de SLA en temporada alta, condiciones específicas por contrato y aprobación requerida para descuentos.
4. Añadir consultas en inglés y casos sin evidencia recuperable antes de ampliar el uso.

El criterio cuantitativo se cumple para el conjunto real evaluado de once casos. Esto no equivale a validación de producción, monitoreo ni aprobación comercial. No se hicieron commits ni PR.

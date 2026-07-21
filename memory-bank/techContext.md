# Tech Context · TrackFlow Monorepo

## Stack actual observado
- Monorepo con carpetas por dominio: uis, services, data, skills, agents, etc.
- Hito 2 de logica de negocio en TypeScript dentro de src/types y src/utils.
- Entorno principal de frontend esperado: Next.js + TypeScript.

## Restricciones tecnicas activas
- Toda API nueva debe vivir en services.
- No confundir .agents (configuracion de agentes) con agents/ y skills/ de producto.
- Reutilizar codigo existente: integrar logica de src por import, sin duplicacion.

## Integracion de logica Hito 2
Fuentes de verdad actuales:
- src/types/models.ts
- src/utils/collections.ts
- src/utils/search.ts
- src/utils/transformations.ts
- src/utils/validations.ts

Uso previsto en backoffice:
- Mostrar metricas operativas (pedidos, devoluciones, incidencias, consultas).
- Ejecutar funciones de reporte, filtro y busqueda sobre datos de ejemplo.
- Renderizar resultados en UI y no solo en consola.

## Convenciones de trabajo
- Cada app UI debe vivir en su subcarpeta dentro de uis.
- Cada app debe incluir scripts dev/build/lint y TS estricto.
- Documentar decisiones clave en memory-bank/progress.md.
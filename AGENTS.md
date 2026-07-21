# AGENTS · Protocolo Operativo del Monorepo

Este archivo define como debe operar cualquier agente de codigo en este repositorio.

## 1) Lectura obligatoria al inicio de cada sesion
Antes de editar codigo, el agente debe leer en este orden:
1. CONTEXT.md
2. company-choice.md
3. memory-bank/projectbrief.md
4. memory-bank/techContext.md
5. memory-bank/progress.md
6. README.md de la raiz
7. README.md de cada carpeta que vaya a modificar

Si encuentra conflicto entre documentos, CONTEXT.md y company-choice.md tienen prioridad de negocio.

## 2) Flujo obligatorio antes de cada commit
El agente debe seguir este flujo minimo, ordenado y explicito:
1. Auditar alcance: listar que archivos se modificaran y por que.
2. Implementar cambios por fases pequenas y coherentes.
3. Verificar calidad: ejecutar build/lint/tests aplicables y corregir errores.
4. Revisar impacto: confirmar que no hay duplicacion de codigo ni ruptura de arquitectura.
5. Actualizar memoria: registrar decisiones y estado en memory-bank/progress.md.
6. Entregar resumen: cambios, validaciones, riesgos pendientes y siguientes pasos.

No se debe commitear si falla alguna validacion critica.

## 3) Rutas protegidas (requieren confirmacion explicita del desarrollador)
El agente NO puede modificar sin confirmacion explicita:
- CONTEXT.md
- company-choice.md
- .env.local
- Cualquier archivo en infra/
- Cualquier archivo en workflows/
- Cualquier secreto o credencial

## 4) Reglas de arquitectura
- Toda API nueva debe vivir dentro de services/.
- .agents/ es solo para configuracion de agentes de desarrollo.
- agents/ y skills/ son activos de producto/plataforma y no se deben mezclar con .agents/.
- Reutilizar codigo existente por import; evitar copiar-pegar logica.

## 5) Criterio de alineacion TrackFlow
Las decisiones tecnicas deben priorizar:
- CX automatizado para consultas de pedido, tracking y devolucion.
- Operacion binacional US/ES.
- Visibilidad operativa en tiempo real y trazabilidad.
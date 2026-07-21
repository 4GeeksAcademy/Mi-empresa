# Project Brief · TrackFlow Tech

## Empresa y contexto
TrackFlow es una empresa de logistica de ultima milla y gestion de almacenes con operacion en Estados Unidos (Los Angeles) y Espana (Zaragoza). El negocio sufre por procesos manuales, baja visibilidad y sistemas fragmentados.

## Problema prioritario
El 80% de las consultas de clientes en CX son repetitivas (pedido, tracking, devolucion, incidencia) y se responden manualmente por email/WhatsApp/telefono, sin tickets unificados ni base de conocimiento.

## Objetivo del proyecto
Construir una base tecnica AI-ready en monorepo para acelerar entrega de:
- Website corporativo moderno para captacion B2B.
- Backoffice operativo para visualizar logica de negocio y habilitar siguientes hitos.
- Infraestructura de agentes (memoria, reglas y skills) para ejecucion consistente.

## Alcance actual (este hito)
- Infraestructura operativa para agentes en raiz.
- uis/website en Next.js + TypeScript con migracion completa del Hito 1.
- uis/backoffice en Next.js + TypeScript con integracion real de logica Hito 2.

## No objetivo en este hito
- No crear APIs nuevas fuera de necesidades minimas.
- No desplegar infraestructura cloud.
- No implementar aun agente productivo de CX con RAG en produccion.

## Criterio de exito
Al finalizar, cualquier agente puede arrancar una sesion con contexto persistente, ejecutar un flujo de entrega consistente y mantener dos UIs funcionales diferenciadas alineadas al negocio de TrackFlow.
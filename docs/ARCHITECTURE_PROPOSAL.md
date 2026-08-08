# Architecture Proposal · Backend (Milestone 5)

## 1) Contexto de negocio y supuestos clave

### Contexto resumido
TrackFlow opera logistica de ultima milla y almacenes en dos paises (US y ES), con sistemas fragmentados, procesos manuales y poca visibilidad en tiempo real. El mayor dolor operativo inmediato es CX: gran parte de consultas repetitivas sobre pedidos, tracking y devoluciones.

### Prioridades de negocio que guian esta propuesta
- Automatizar CX para consultas de pedido, tracking y devolucion.
- Operar de forma binacional (US/ES) con consistencia de reglas y trazabilidad.
- Mejorar visibilidad operativa en tiempo real para operaciones y direccion.

### Supuestos tecnicos y organizativos
- El monorepo actual se mantiene como base de trabajo para sprint inicial.
- Los frontends existentes (website y backoffice en Next.js) consumiran APIs HTTP del backend.
- El equipo backend inicial es pequeno; se prioriza arquitectura clara y evolucionable sobre complejidad prematura.
- El primer alcance del backend no reemplaza todos los legados de golpe; empieza por unificar lectura y estado de dominios criticos.

## 2) Patron arquitectonico propuesto y justificacion

## Propuesta
Se propone una arquitectura modular monolitica en capas (Clean-ish / Hexagonal pragmatica) implementada con FastAPI.

En terminos practicos:
- Un solo servicio backend desplegable en primera fase (menor overhead operativo).
- Separacion estricta por dominios de negocio (orders, tracking, returns, cx, customers, carriers).
- Capas internas por responsabilidad: API, aplicacion, dominio e infraestructura.

## Por que encaja con TrackFlow ahora
- Reduce tiempo de entrega para el proximo sprint: un despliegue, observabilidad centralizada y menor friccion para equipo pequeno.
- Evita acoplar frontends a sistemas legacy: el backend actua como fachada unificada.
- Mantiene camino de evolucion: cada modulo puede extraerse a microservicio si escala por carga, autonomia o criticidad.
- Permite instrumentar telemetria desde el inicio en un punto unico.

## Criterios para evolucionar en el futuro
Extraer un modulo a servicio independiente solo cuando exista evidencia de:
- Cuello de botella de rendimiento aislado.
- Necesidad de escalado/latencia distinta por dominio.
- Ciclo de despliegue independiente por equipo.
- Riesgo de cambios cruzados en el monolito.

## 3) Alternativas descartadas y trade-offs

## A) Microservicios desde el dia 1
Ventajas:
- Autonomia por dominio y escalado fino.

Desventajas para este contexto:
- Complejidad operativa alta (networking interno, contratos, tracing distribuido, CI/CD multi-servicio).
- Mayor carga para un equipo backend pequeno en fase de arranque.

Decision:
- Descartada para fase inicial. Se conserva como destino evolutivo.

## B) Serverless puro por endpoints
Ventajas:
- Escalado automatico y pago por uso.

Desventajas para este contexto:
- Orquestar integraciones complejas con carriers y reglas de negocio largas puede aumentar cold starts y complejidad de debugging.
- Riesgo de fragmentar demasiado el dominio al inicio.

Decision:
- No prioritaria para nucleo transaccional inicial. Puede usarse despues en jobs/eventos puntuales.

## C) Backend por BFF separado por frontend
Ventajas:
- Optimiza experiencias por canal.

Desventajas para este contexto:
- Duplica reglas de negocio en website/backoffice si no se gobierna bien.

Decision:
- En fase inicial se mantiene API de dominio comun. BFF solo si aparecen necesidades de agregacion especifica por canal.

## 4) Estructura propuesta de modulos, capas y dominios

## Convenciones FastAPI consideradas (practica habitual)
En proyectos FastAPI maduros suele separarse:
- Routers por dominio o recurso.
- Schemas (Pydantic) para request/response.
- Servicios/casos de uso para logica de aplicacion.
- Repositorios/adaptadores para acceso a DB y APIs externas.
- Core/config para settings, seguridad, middlewares y dependencias compartidas.

### Origen explicito de estas convenciones
Esta propuesta se apoya en patrones documentados en fuentes oficiales y de referencia de la comunidad FastAPI:
- Documentacion oficial de FastAPI: estructura por modulos, APIRouter, dependencies y settings.
- Ejemplo oficial Full Stack FastAPI Template (organizacion por app/api/core/models/schemas).
- Practicas extendidas en proyectos de produccion: separacion por dominio y capa para mantener testabilidad y evolucion.

Como influyen en esta propuesta:
- APIRouter + versionado -> carpeta api/v1/endpoints por dominio.
- Dependency Injection -> core/dependencies.py para dependencias compartidas y seguridad.
- Schemas Pydantic -> carpeta schemas para contratos de entrada/salida.
- Configuracion centralizada -> core/config.py para settings por entorno.

## Estructura de carpetas propuesta (dentro de services/)

```text
services/
  backend/
    app/
      main.py
      api/
        v1/
          router.py
          endpoints/
            orders.py
            tracking.py
            returns.py
            cx.py
            customers.py
            carriers.py
            health.py
      core/
        config.py
        logging.py
        security.py
        dependencies.py
        middleware.py
      domain/
        orders/
          entities.py
          rules.py
        tracking/
          entities.py
          rules.py
        returns/
          entities.py
          rules.py
        cx/
          entities.py
          rules.py
        carriers/
          entities.py
          rules.py
      application/
        orders/
          use_cases.py
        tracking/
          use_cases.py
        returns/
          use_cases.py
        cx/
          use_cases.py
      infrastructure/
        db/
          models.py
          repositories/
        external/
          carriers/
            ups_client.py
            fedex_client.py
            mrw_client.py
            seur_client.py
        messaging/
          events.py
      schemas/
        orders.py
        tracking.py
        returns.py
        cx.py
      tests/
        unit/
        integration/
```

### Separacion de responsabilidades
- API (routers): valida entrada/salida, no contiene reglas de negocio complejas.
- Application: orquesta casos de uso (workflow de negocio).
- Domain: reglas puras y lenguaje de negocio.
- Infrastructure: detalles tecnicos (DB, clientes externos, colas).
- Core: configuracion transversal y dependencias compartidas.

## 5) Propuesta de rutas/endpoints FastAPI por dominio (sin implementacion)

Prefijo base: /api/v1

### Health y observabilidad
- GET /health
- GET /ready
- GET /metrics (protegido, para scraping interno)

### Orders
- GET /orders/{order_id}
- GET /orders (filtros: country, status, date_from, date_to, customer_id)
- POST /orders/intake (ingesta estandarizada de pedido)
- PATCH /orders/{order_id}/status

### Tracking
- GET /tracking/{tracking_id}
- GET /tracking/order/{order_id}
- POST /tracking/refresh (forzar sincronizacion puntual con carrier)
- GET /tracking/events (filtros por carrier, fecha, estado)

### Returns
- POST /returns/evaluate (evaluacion automatica segun reglas)
- POST /returns
- GET /returns/{return_id}
- PATCH /returns/{return_id}/status
- GET /returns (filtros por motivo, pais, cliente, estado)

### CX
- POST /cx/inquiries/resolve (resolver consulta repetitiva)
- POST /cx/inquiries/escalate
- GET /cx/inquiries/{inquiry_id}
- GET /cx/kb/search (busqueda semantica futura)

### Customers (B2B/B2C)
- GET /customers/{customer_id}
- GET /customers/{customer_id}/orders
- GET /customers/{customer_id}/returns

### Carriers
- GET /carriers
- POST /carriers/recommend (destino, peso, urgencia)
- GET /carriers/performance (OTD, incidencias, coste por kg)

## Criterio de agrupacion de routers
Los routers se agrupan por dominio de negocio, no por tipo tecnico. Esto minimiza acoplamiento cognitivo y mejora ownership por modulo.

## 6) Integracion con frontends existentes del monorepo

## Modelo de comunicacion
- Website (B2B captacion y formularios): consume endpoints de contacto/lead y consultas de estado limitadas.
- Backoffice (operaciones): consume endpoints de orders, tracking, returns, carriers y CX.
- Todos los contratos via JSON con versionado /api/v1.

## CORS y seguridad de origen
- Permitir solo origenes explicitos por entorno (dev/staging/prod).
- No usar wildcard en produccion.
- Habilitar credenciales solo cuando sea estrictamente necesario.

## Variables de entorno (separacion frontend/backend)
Backend:
- APP_ENV
- API_PORT
- DATABASE_URL
- REDIS_URL
- CORS_ALLOWED_ORIGINS
- CARRIER_API_KEYS_* (gestionado por secreto)
- LOG_LEVEL

Frontend:
- NEXT_PUBLIC_API_BASE_URL
- NEXT_PUBLIC_APP_ENV

Principio:
- Variables NEXT_PUBLIC_* solo para datos no sensibles.
- Secretos exclusivamente en backend/infra.

## Monorepo vs repos separados (analisis para este caso)
Monorepo (actual) ventajas:
- Cambios coordinados frontend-backend en un mismo PR.
- Reuso de tipos/contratos y documentacion centralizada.
- Menor friccion para equipo pequeno en etapa de definicion.

Monorepo riesgos:
- Pipelines pueden crecer en tiempo si no se segmentan por carpetas.
- Riesgo de acoplamiento accidental entre apps.

Conclusion:
- Mantener monorepo en fase inicial, con limites claros por carpetas y ownership.
- Revisar split a multi-repo solo si aparecen bloqueos de autonomia por equipo.

## 7) Decisiones tecnicas iniciales para arrancar sprint

1. Crear servicio backend dentro de services/backend con estructura por capas y dominios.
2. Definir contrato minimo OpenAPI para dominios orders, tracking, returns y cx antes de implementar logica compleja.
3. Implementar autenticacion de API para canales internos y trazabilidad con request-id.
4. Activar logging estructurado y correlacion de eventos desde el dia 1.
5. Instrumentar metricas minimas: latencia por endpoint, tasa de error, volumen por dominio.
6. Introducir pruebas unitarias de casos de uso y pruebas de contrato de API.
7. Definir politica de errores homogenea (codigos, detalle tecnico interno, mensaje cliente).
8. Arrancar con integraciones carrier via adaptadores desacoplados para evitar lock-in de proveedor.

### Justificacion de decisiones frente al alcance del curso
- Se priorizan decisiones de arquitectura y organizacion (capas, routers, contratos, observabilidad), no detalles de infraestructura avanzada.
- No se introduce codigo funcional de endpoints en este entregable; se mantiene en nivel de diseno tecnico.
- La propuesta mantiene coherencia con el alcance del hito: preparar base backend clara para implementar en siguientes sprints.

## 8) Riesgos y puntos de atencion con mitigacion

## Riesgo 1: divergencia de reglas de negocio entre paises
Impacto:
- Inconsistencia en devoluciones, SLA y estados logísticos.

Mitigacion:
- Modelar reglas por pais/cliente en capa de dominio con configuracion versionada.
- Agregar pruebas de regresion por escenario US/ES.

## Riesgo 2: acoplamiento excesivo al legado o a APIs de carriers
Impacto:
- Cambios externos rompen flujos internos y aumentan tiempo de respuesta ante incidencias.

Mitigacion:
- Usar adaptadores por carrier + contratos internos canonicos de tracking/eventos.
- Implementar reintentos, circuit breaker y colas para desacoplar picos/fallos.

## Riesgo 3: debt de observabilidad temprana
Impacto:
- Incidencias sin diagnostico rapido entre Zaragoza y Los Angeles.

Mitigacion:
- Logging estructurado con correlacion, dashboards basicos y alertas desde primer sprint.

## Riesgo 4: crecimiento desordenado del monorepo
Impacto:
- Builds lentas y ownership difuso.

Mitigacion:
- Reglas de ownership por carpeta, pipelines por cambios y politicas de contratos API.

## 9) Conflictos potenciales en el equipo (y como evitarlos)

- Conflicto arquitectura (microservicios ya vs modular monolito): acordar criterios de extraccion basados en metricas, no opiniones.
- Conflicto ownership frontend-backend: definir responsables por dominio y contrato de API versionado.
- Conflicto velocidad vs calidad: exigir Definition of Done minima con pruebas y observabilidad por endpoint critico.

## 10) Cierre

Esta propuesta prioriza impacto de negocio inmediato (CX, tracking, devoluciones), minimiza complejidad de arranque y mantiene un camino claro de evolucion. La recomendacion es iniciar con backend modular en FastAPI dentro de services, contratos de API versionados y observabilidad desde el primer sprint.

# Auditoria de rendimiento y mantenibilidad - 2026-09-17

## Alcance

- `uis/website`: rutas `/` y `/apply`.
- `uis/backoffice`: ruta `/` y componentes de autenticacion relacionados.
- No se modificaron rutas protegidas, APIs, contratos ni la arquitectura del monorepo.

## Skill utilizada

Se instalo `addyosmani/web-quality-skills`, skill `core-web-vitals`, en `.agents/skills/core-web-vitals`.

Reglas aplicadas:

- Priorizar LCP, TBT/INP, CLS y recursos que bloquean el renderizado antes de auditorias secundarias.
- Verificar que las fuentes criticas se sirvan con `next/font` y evitar preloads manuales de recursos que no existen.
- Corregir metadatos o directivas de indexacion solo cuando la causa sea verificable.
- Diferir JavaScript no critico solo si se identifica una carga no esencial concreta.

## Medicion

### Baseline disponible

Las capturas de `audit/before` proporcionan el baseline:

| Ruta y perfil | Performance | LCP | TBT | SEO |
| --- | ---: | ---: | ---: | ---: |
| Website `/` movil | 90 | 3.4 s | No registrado | 60 |
| Backoffice `/` escritorio | 83 | No registrado | 370 ms | 60 |
| Backoffice `/` movil | 72 | No registrado | 1,750 ms | 60 |

Tambien se revisaron las capturas desktop y movil de `/apply`; no muestran una regresion visual atribuible al formulario.

### Limitacion de medicion posterior

Lighthouse no pudo ejecutarse en este contenedor: no hay Chrome del sistema y el Chromium descargado por Playwright falla al cargar por faltar `libatk-1.0.so.0`. Por tanto no se inventan metricas posteriores ni se comparan puntuaciones no reproducibles.

Se creo el `.env` local a partir de la plantilla versionada. Compose construye los dos servicios y, tras iniciar los contenedores creados, el backend queda `healthy`; las rutas `/`, `/apply`, `/robots.txt` y `/` del backoffice responden HTTP 200 desde el contenedor `interfaces`. La publicacion de puertos hacia el host resetea conexiones y `http://backend:8000/health` agota el timeout desde `interfaces`, una limitacion de red del Docker anidado ya registrada en el proyecto. No se atribuye ese comportamiento a las UIs ni se modifica la configuracion de infraestructura protegida.


## Hallazgos de mantenibilidad

### 1. Carcasa repetida de autenticacion - implementado

**Aparece en:** `uis/backoffice/app/login/page.tsx`, `uis/backoffice/app/register/page.tsx`, `uis/backoffice/app/forgot-password/page.tsx`, `uis/backoffice/app/reset-password/page.tsx` y `uis/backoffice/app/account/change-password/page.tsx`.

**Evidencia:** cada pagina repetia el mismo `main` con `ops-bg`, centrado vertical, y tarjeta con las mismas clases de ancho, borde, fondo, padding y sombra.

**Por que refactorizar:** cambios de responsividad, accesibilidad visual o estilo de las pantallas publicas requerian editar cinco implementaciones identicas.

**Abstraccion:** `AuthPageShell` recibe `children` y centraliza exclusivamente la carcasa visual. No concentra estado, validacion ni navegacion de formularios.

**Resultado e impacto:** se implemento `uis/backoffice/components/auth-page-shell.tsx` y se adopto en login, registro y recuperacion. Es un cambio de bajo riesgo: conserva el DOM interno y los controladores de cada formulario. Las dos pantallas pendientes pueden migrarse en una tarea posterior sin cambiar la API del componente.

### 2. Construccion de cabeceras autenticadas en el analizador - pendiente

**Aparece en:** `uis/backoffice/components/incidents-analyzer.tsx`, en `onSubmit` y `onDownload`.

**Evidencia:** ambos flujos leen el token de `localStorage`, crean `Record<string, string>` y añaden condicionalmente `Authorization: Bearer ...` antes de llamar a `fetch`.

**Por que refactorizar:** la regla de autorizacion puede divergir entre descarga y analisis; ya existe `getToken()` en `uis/backoffice/lib/auth.ts` como fuente de verdad para esa lectura.

**Abstraccion propuesta:** un helper local `getAuthorizationHeaders()` en `lib/auth.ts`, que retorne un objeto vacio sin sesion o la cabecera `Authorization` con el token. El analizador lo invocaria en ambas operaciones.

**Impacto y riesgo:** bajo; reduce repeticion sin cambiar rutas ni semantica HTTP. Queda pendiente porque no es una correccion requerida por Core Web Vitals y no debe mezclarse con la mejora medida de rendimiento.

## Hallazgos de rendimiento y SEO

### Website: SEO 60

**Causa confirmada:** `uis/website/app/layout.tsx` solo declaraba titulo y descripcion, y no existia una directiva `robots.txt`. Esto explica una parte verificable de la puntuacion SEO baja, independiente de LCP.

**Correccion requerida aplicada:** se anadio `uis/website/app/robots.ts`, que genera `robots.txt` con permiso de rastreo para `/`. Verificacion HTTP posterior: `User-Agent: *` y `Allow: /`.

No se anadieron canonical, sitemap u OpenGraph: no hay un dominio de produccion fiable en el repositorio y fabricarlo generaria URLs incorrectas.

### Website: LCP movil de 3.4 s

La landing no carga imagenes de hero y utiliza `next/font/google`, que autoalberga y precarga la fuente. Los cinco pesos configurados se usan en la pagina. No se encontro una correccion requerida que pueda aplicarse sin eliminar contenido, alterar el diseno o introducir una optimizacion especulativa.

### Backoffice: TBT alto

El dashboard inicial se renderiza como Server Component y el analizador de CSV no se carga en `/`; no hay una carga no critica demostrada que se pueda diferir para esa ruta. La medicion posterior esta bloqueada por Chromium, por lo que no se aplica code splitting ni memoizacion especulativa sin evidencia de una tarea larga en el perfil de Lighthouse.

## Validaciones

- `npm ci` en `uis/website` y `uis/backoffice`: correcto. npm informa 3 vulnerabilidades transitivas por proyecto (2 altas y 1 critica); no pertenecen a cambios de esta auditoria.
- `npm run lint` en `uis/backoffice`: correcto tras extraer `AuthPageShell`.
- `npm run lint` en `uis/website`: correcto tras anadir `robots.ts`.
- `npm run build` en `uis/website`: correcto.
- `npm run build` en `uis/backoffice`: correcto.
- Servidores de produccion: HTTP 200 para `/`, `/apply` y `/` del backoffice.
- Docker: backend `healthy`; website `/`, `/apply`, `/robots.txt` y backoffice `/` responden HTTP 200 dentro de `interfaces`.
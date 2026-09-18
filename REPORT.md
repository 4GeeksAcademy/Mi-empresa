# Informe de auditoria frontend - 2026-09-17

## Alcance

Auditoria de `uis/website` (rutas `/` y `/apply`) y `uis/backoffice` (ruta `/` y flujos de autenticacion), centrada en Core Web Vitals, SEO y mantenibilidad.

## Correcciones aplicadas

### 1. Carcasa reutilizable para autenticacion del backoffice

**Cambio:** se creo `uis/backoffice/components/auth-page-shell.tsx` y se utilizo en las pantallas de inicio de sesion, registro y recuperacion de contrasena.

**Problema corregido:** estas paginas repetian el mismo contenedor de pantalla completa, fondo `ops-bg` y tarjeta de formulario. Cualquier ajuste visual o responsive exigia cambios equivalentes en varias ubicaciones.

**Resultado:** la presentacion comun queda centralizada en `AuthPageShell`, mientras cada pagina conserva su estado, validaciones, peticiones y navegacion. Es una correccion de mantenibilidad de bajo riesgo, sin alterar los flujos de autenticacion.

### 2. Directiva de rastreo para el website

**Cambio:** se anadio `uis/website/app/robots.ts`.

**Problema corregido:** la auditoria SEO mostraba una puntuacion de 60 y el sitio no exponia una directiva `robots.txt` verificable.

**Resultado:** Next.js genera `/robots.txt` con:

```text
User-Agent: *
Allow: /
```

El archivo fue comprobado con respuesta HTTP 200 desde el contenedor de interfaces. No se anadieron canonical, sitemap ni OpenGraph porque el repositorio no define un dominio de produccion fiable y no se deben generar URLs ficticias.

### 3. Entorno Docker local para la auditoria

**Cambio:** se creo `.env` local a partir de `.env.example`, con valores de desarrollo y una clave local.

**Problema corregido:** Docker Compose no podia cargar los servicios al faltar el archivo requerido por `env_file`.

**Resultado:** las imagenes se construyen y los contenedores quedan ejecutandose; `backend` alcanza estado `healthy`. Dentro de `interfaces`, website `/`, formulario `/apply`, `/robots.txt` y backoffice `/` responden HTTP 200.

## Comparativa de puntuaciones

| Ruta y perfil | Performance antes | Performance despues | LCP antes | LCP despues | TBT antes | TBT despues | SEO antes | SEO despues |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Website `/` movil | 90 | No disponible | 3.4 s | No disponible | No registrado | No disponible | 60 | No disponible |
| Backoffice `/` escritorio | 83 | No disponible | No registrado | No disponible | 370 ms | No disponible | 60 | No disponible |
| Backoffice `/` movil | 72 | No disponible | No registrado | No disponible | 1,750 ms | No disponible | 60 | No disponible |

Las puntuaciones iniciales proceden de las capturas Lighthouse en `audit/before`.

No hay valores posteriores porque el entorno no dispone de Chrome/Chromium utilizable: el binario descargado por Playwright no inicia por la dependencia del sistema `libatk-1.0.so.0`. Por rigor, no se atribuyen mejoras numericas a cambios que no pudieron medirse bajo condiciones equivalentes.

## Valoracion de impacto

La correccion con mayor impacto inmediato es `robots.ts`: soluciona una carencia SEO concreta, observable y verificable sin modificar el diseno ni el comportamiento del sitio. Es probable que mejore la cobertura de auditorias SEO relacionadas con indexabilidad, pero la puntuacion exacta debe confirmarse con una nueva ejecucion de Lighthouse.

La correccion con mayor impacto sostenido es `AuthPageShell`: elimina duplicacion en un flujo transversal del backoffice y reduce el coste y el riesgo de futuros cambios visuales en autenticacion.

No se aplicaron optimizaciones especulativas para LCP o TBT. El LCP movil del website y el TBT del backoffice requieren una traza de navegador o una medicion Lighthouse posterior que identifique el recurso o tarea larga responsable antes de cambiar fuentes, carga de componentes o estilos.

## Validaciones realizadas

- `npm run lint` en `uis/website` y `uis/backoffice`: correcto.
- `npm run build` en `uis/website` y `uis/backoffice`: correcto.
- Docker: `backend` en estado `running healthy`; `interfaces` en estado `running`.
- Rutas verificadas dentro de Docker: website `/`, `/apply`, `/robots.txt` y backoffice `/` con HTTP 200.
- `git diff --check`: correcto.

## Riesgos pendientes

- La medicion Lighthouse posterior permanece pendiente de un entorno con navegador funcional.
- La red Docker anidada mantiene una limitacion: la exposicion de puertos al host y la comunicacion `interfaces -> backend` pueden agotar timeout, aunque ambas UIs responden internamente y el backend esta saludable.
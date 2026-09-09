# Plan de pruebas AUTH-088

## Objetivo

Las suites de autenticacion validan decisiones de negocio de las funciones de
registro, sesion, autorizacion JWT, recuperacion de contrasena y perfil. No
verifican serializacion HTTP ni comportamiento interno de FastAPI.

## Instalacion y ejecucion

Desde `services/api`, sincroniza el entorno y ejecuta la suite:

```bash
uv sync --all-groups
uv run pytest
uv run pytest --cov
```

La cobertura objetivo de los modulos de autenticacion es al menos el 70%.

Desde `src`, instala y ejecuta las pruebas de utilidades TypeScript:

```bash
npm install
npm test -- --coverage
```

La configuracion `jest.config.cjs` usa `ts-jest` en modo ESM y cubre busqueda,
colecciones, transformaciones y validaciones de dominio.

## Suites y escenarios

### Registro y administracion de usuarios (`test_register.py`)

- `create_user`: crea usuario y perfil opcional, comprobando que la contrasena
  queda hasheada. Cubre el alta normal.
- `create_user`: rechaza email duplicado. Evita identidades ambiguas.
- Modelos de usuario: normalizan email y rechazan email sin `@` o contrasena
  demasiado corta. Cubren los limites de entrada antes de persistir.
- `update_user`: permite a un administrador actualizar un usuario, rechaza la
  escalada de rol por un usuario normal y rechaza un usuario inexistente.
- `delete_user`: elimina el perfil asociado junto al usuario y rechaza un ID
  inexistente. Evita datos de perfil huerfanos.

### Inicio de sesion y token (`test_login.py`, `test_token.py`)

- `login`: emite un token para credenciales validas, y rechaza email ausente,
  contrasena incorrecta y usuario inactivo. Evita acceso no autorizado.
- `create_access_token` y `get_current_user`: validan un token correcto y
  rechazan tokens expirados, malformados, sin sujeto o asociados a usuarios
  inactivos. Cubren las fronteras de seguridad JWT.
- `get_current_admin`: permite el rol admin y rechaza los demas roles.

### Recuperacion y cambio de contrasena (`test_auth_password.py`)

- `forgot_password`: crea y envia token solo para usuarios activos, pero
  devuelve siempre el mismo mensaje para email inexistente o inactivo. Evita
  enumeracion de cuentas.
- `reset_password`: actualiza una contrasena con token valido y rechaza token
  inexistente, usado o expirado, asi como usuario eliminado. Protege el ciclo
  de vida del token.
- `change_password`: actualiza cuando la contrasena actual coincide y rechaza
  contrasena incorrecta y usuario inexistente.

### Perfil autenticado (`test_profile.py`)

- `get_my_profile`: devuelve un perfil existente y rechaza uno ausente.
- `update_my_profile`: aplica los campos presentes, conserva el perfil si no
  hay cambios y rechaza un perfil inexistente. Evita actualizaciones perdidas
  y perfiles creados implicitamente.

### Utilidades TypeScript (`src/tests/utils.test.ts`)

- Busquedas: encuentra pedidos existentes y devuelve `null` para objetivos
  ausentes. Protege las consultas operativas frente a resultados inventados.
- Colecciones: filtra limites inclusivos, agrupa destinos y aplica ordenacion
  por prioridad sin mutar el origen. Evita cambios colaterales en la UI.
- Transformaciones: calcula totales, promedios, extremos y categorias vacias.
  Protege los KPIs del backoffice.
- Validaciones: acepta registros trazables y rechaza estados finales sin fecha,
  transportistas incompatibles y respuestas automaticas sin contenido. Estos
  casos fueron seleccionados durante la revision asistida para cubrir reglas
  que pueden pasar inadvertidas en flujos nominales.

## Tareas extra API-042 y FE-019

### Endpoints de backoffice (`test_backoffice_suppliers.py`, `test_backoffice_incidents.py`)

- Proveedores: registra un proveedor valido, aplica aliases `country` y
  `category`, devuelve 404 si no existe y encapsula fallos del repositorio en
  un error de negocio. Cubre alta normal, filtros opcionales y fallos de
  persistencia.
- Incidencias: crea una incidencia valida, entrega los filtros de listado al
  repositorio, rechaza una incidencia ausente y una transicion de estado no
  permitida. Cubre el ciclo normal, los limites de consulta y una regla de
  negocio invalida.
- Ejecucion y cobertura enfocada:

```bash
cd services/api
uv run pytest tests/test_backoffice_suppliers.py tests/test_backoffice_incidents.py --cov=routes.suppliers --cov=routes.incidents --cov-report=term-missing -q
```

Resultado: 7 pruebas aprobadas. Cobertura: `routes/suppliers.py` 77%,
`routes/incidents.py` 66% y total 72%, superior al objetivo de 60%.

### Helpers frontend del backoffice (`uis/backoffice/tests/auth.test.ts`)

- `isTokenExpired`: acepta un JWT vigente y trata tokens malformados o
  expirados como no validos. Evita sesion con tokens no confiables.
- `verifyToken`: conserva un token valido y elimina uno vencido de
  `localStorage`. Protege el cierre de sesion automatico.
- `login`: devuelve el token de una respuesta correcta y propaga el detalle
  de una respuesta fallida. Evita ocultar el error de autenticacion al usuario.
- Ejecucion:

```bash
cd uis/backoffice
npm test -- --coverage
npm run lint
npx tsc --noEmit
```

Resultado: 3 pruebas aprobadas; 48.1% statements, 28% branches, 30% functions
y 53.62% lines sobre `lib/auth.ts`.

## Aislamiento

Cada prueba usa una ruta TinyDB temporal mediante `TRACKFLOW_AUTH_DB_PATH` y
limpia las factorias cacheadas. Las dependencias externas se sustituyen con
mocks: el envio de email, el reloj/token cuando aplica y hashing costoso en
las pruebas de rutas. Esto mantiene la suite determinista y sin servicios
externos.

## Bugs detectados

- Se detecto una deriva de dependencias: `requirements.txt` fijaba
  `bcrypt==4.1.2` para compatibilidad con `passlib`, pero `pyproject.toml` no.
  Esto hacia que el entorno creado por uv instalara una version incompatible.
  Se fijo la misma version en `pyproject.toml`.
- La primera ejecucion de la suite revelo una firma incorrecta en un mock de
  prueba; se corrigio en la propia suite y no afectaba a la aplicacion.
- La configuracion de Jest requirio habilitar `--experimental-vm-modules` para
  ejecutar TypeScript ESM con `ts-jest`; se incorporo al script `npm test`.
- La revision asistida detecto que jsdom no incluye `fetch` ni `Response` en
  este entorno. Las pruebas FE-019 usan dobles locales con el contrato minimo
  (`ok` y `json`) para aislar los helpers de autenticacion sin servicios web.
# Regla: Reutilizar logica existente por import

## Alcance
- Siempre activa para cualquier cambio en uis/, services/, agents/ y skills/.

## Regla
- Antes de crear funciones nuevas, buscar implementaciones equivalentes existentes en el monorepo.
- Si existe una implementacion valida, importarla desde su ubicacion original.
- Esta prohibido duplicar logica de negocio por copia de codigo salvo aprobacion explicita del desarrollador.

## Justificacion
TrackFlow necesita coherencia operativa y mantenimiento simple entre equipos en dos paises. Duplicar logica genera divergencias y errores de negocio.

## Verificacion
Se considera cumplida cuando:
1. Los nuevos modulos referencian funciones compartidas existentes por import.
2. No se introducen clones funcionales de utilidades ya presentes.
3. El resumen de cambios documenta explicitamente que piezas se reutilizaron.
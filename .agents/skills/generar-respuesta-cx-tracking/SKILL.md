---
name: generar-respuesta-cx-tracking
summary: Genera una respuesta automatica de primera linea para consultas de pedido/tracking/devolucion/incidencia.
---

# Objetivo unico
Generar una respuesta de CX clara y accionable a partir de una consulta de cliente y el estado operativo disponible.

# Inputs
1. consulta
- tipoConsulta: PEDIDO | TRACKING | DEVOLUCION | INCIDENCIA
- idioma: es | en
- canal: EMAIL | WHATSAPP
- mensaje: string
- idPedido: string

2. contexto_operativo
- estadoPedido: string
- estadoDevolucion: string | null
- estadoIncidencia: string | null
- fechaEstimada: string | null
- ultimoEvento: string | null

3. politicas
- tono: string
- permitirEscalado: boolean
- incluirSiguientesPasos: boolean

# Output esperado
Objeto JSON con:
- estado: RESPONDIDA_AUTOMATICAMENTE | ESCALADA
- idioma: es | en
- respuesta: string
- razones: string[]
- accionesSugeridas: string[]

# Proceso
1. Validar inputs obligatorios.
2. Determinar plantilla por tipoConsulta e idioma.
3. Inyectar estado operativo actual y siguiente paso.
4. Si faltan datos criticos y permitirEscalado=true, devolver estado ESCALADA.

# Criterios de aceptacion verificables
1. Si faltan tipoConsulta, idioma o idPedido, la skill devuelve estado ESCALADA.
2. La respuesta siempre menciona estado actual y proximo paso cuando incluirSiguientesPasos=true.
3. El idioma del output coincide con el input.
4. El output cumple exactamente el esquema definido en la seccion Output esperado.
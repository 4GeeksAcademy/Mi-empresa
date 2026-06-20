export type PaisOperacion = "ES" | "US";

export type Urgencia = "BAJA" | "MEDIA" | "ALTA" | "URGENTE";

export type EstadoTrackingPedido =
	| "PENDIENTE"
	| "EN_PREPARACION"
	| "EN_TRANSITO"
	| "ENTREGADO"
	| "INCIDENCIA"
	| "DEVUELTO";

export type EstadoDevolucion =
	| "SOLICITADA"
	| "APROBADA"
	| "RECHAZADA"
	| "EN_RECOGIDA"
	| "RECIBIDA"
	| "CERRADA";

export type EstadoIncidenciaTransportista =
	| "ABIERTA"
	| "EN_GESTION"
	| "RESUELTA";

export type TipoCliente = "B2B" | "CONSUMIDOR_FINAL";

export type CanalContacto = "EMAIL" | "WHATSAPP";

export type IdiomaCliente = "es" | "en";

export type TipoConsulta = "PEDIDO" | "TRACKING" | "DEVOLUCION" | "INCIDENCIA";

export type EstadoConsultaAgente =
	| "RECIBIDA"
	| "RESPONDIDA_AUTOMATICAMENTE"
	| "ESCALADA";

export interface Transportista {
	idTransportista: string;
	nombre: string;
	paisesDisponibles: PaisOperacion[];
	destinosDisponibles: PaisOperacion[];
	activo: boolean;
	pesoMaximoKg: number;
	urgenciasSoportadas: Urgencia[];
	apiTrackingDisponible: boolean;
}

export interface Pedido {
	idPedido: string;
	idCliente: string;
	tipoCliente: TipoCliente;
	origen: PaisOperacion;
	destino: PaisOperacion;
	idTransportista: string;
	pesoKg: number;
	urgencia: Urgencia;
	estadoTracking: EstadoTrackingPedido;
	fechaCreacion: string;
	fechaEntregaEstimada: string;
	fechaEntregaReal: string | null;
}

export interface Devolucion {
	idDevolucion: string;
	idPedido: string;
	estadoDevolucion: EstadoDevolucion;
	motivo: string;
	fechaSolicitud: string;
	fechaResolucion: string | null;
}

export interface IncidenciaTransportista {
	idIncidencia: string;
	idPedido: string;
	idTransportista: string;
	descripcion: string;
	estadoIncidencia: EstadoIncidenciaTransportista;
	fechaReporte: string;
	fechaResolucion: string | null;
}

export interface ConsultaCliente {
	idConsulta: string;
	idCliente: string;
	tipoCliente: TipoCliente;
	canal: CanalContacto;
	idioma: IdiomaCliente;
	tipoConsulta: TipoConsulta;
	idPedido: string | null;
	mensaje: string;
	fechaConsulta: string;
	estadoAgente: EstadoConsultaAgente;
	respuestaAutomatica: string | null;
}

export const TRANSPORTISTAS_EJEMPLO: Transportista[] = [
	{
		idTransportista: "TR-US-UPS",
		nombre: "UPS",
		paisesDisponibles: ["US"],
		destinosDisponibles: ["US"],
		activo: true,
		pesoMaximoKg: 70,
		urgenciasSoportadas: ["BAJA", "MEDIA", "ALTA", "URGENTE"],
		apiTrackingDisponible: true,
	},
	{
		idTransportista: "TR-ES-SEUR",
		nombre: "SEUR",
		paisesDisponibles: ["ES"],
		destinosDisponibles: ["ES"],
		activo: true,
		pesoMaximoKg: 50,
		urgenciasSoportadas: ["BAJA", "MEDIA", "ALTA"],
		apiTrackingDisponible: true,
	},
	{
		idTransportista: "TR-INT-DHL",
		nombre: "DHL",
		paisesDisponibles: ["ES", "US"],
		destinosDisponibles: ["ES", "US"],
		activo: true,
		pesoMaximoKg: 80,
		urgenciasSoportadas: ["MEDIA", "ALTA", "URGENTE"],
		apiTrackingDisponible: true,
	},
];

export const PEDIDOS_EJEMPLO: Pedido[] = [
	{
		idPedido: "P-1001",
		idCliente: "CL-001",
		tipoCliente: "B2B",
		origen: "US",
		destino: "US",
		idTransportista: "TR-US-UPS",
		pesoKg: 2.4,
		urgencia: "MEDIA",
		estadoTracking: "EN_TRANSITO",
		fechaCreacion: "2026-06-15T08:30:00.000Z",
		fechaEntregaEstimada: "2026-06-18T18:00:00.000Z",
		fechaEntregaReal: null,
	},
	{
		idPedido: "P-1002",
		idCliente: "CL-002",
		tipoCliente: "CONSUMIDOR_FINAL",
		origen: "ES",
		destino: "ES",
		idTransportista: "TR-ES-SEUR",
		pesoKg: 1.1,
		urgencia: "ALTA",
		estadoTracking: "ENTREGADO",
		fechaCreacion: "2026-06-14T10:00:00.000Z",
		fechaEntregaEstimada: "2026-06-16T18:00:00.000Z",
		fechaEntregaReal: "2026-06-16T13:40:00.000Z",
	},
	{
		idPedido: "P-1003",
		idCliente: "CL-003",
		tipoCliente: "CONSUMIDOR_FINAL",
		origen: "US",
		destino: "ES",
		idTransportista: "TR-INT-DHL",
		pesoKg: 4.8,
		urgencia: "URGENTE",
		estadoTracking: "INCIDENCIA",
		fechaCreacion: "2026-06-13T07:10:00.000Z",
		fechaEntregaEstimada: "2026-06-17T18:00:00.000Z",
		fechaEntregaReal: null,
	},
];

export const DEVOLUCIONES_EJEMPLO: Devolucion[] = [
	{
		idDevolucion: "D-2001",
		idPedido: "P-1002",
		estadoDevolucion: "SOLICITADA",
		motivo: "Producto danado",
		fechaSolicitud: "2026-06-17T09:20:00.000Z",
		fechaResolucion: null,
	},
];

export const INCIDENCIAS_EJEMPLO: IncidenciaTransportista[] = [
	{
		idIncidencia: "I-3001",
		idPedido: "P-1003",
		idTransportista: "TR-INT-DHL",
		descripcion: "Retraso por bloqueo aduanero",
		estadoIncidencia: "EN_GESTION",
		fechaReporte: "2026-06-17T11:00:00.000Z",
		fechaResolucion: null,
	},
];

export const CONSULTAS_EJEMPLO: ConsultaCliente[] = [
	{
		idConsulta: "Q-4001",
		idCliente: "CL-003",
		tipoCliente: "CONSUMIDOR_FINAL",
		canal: "WHATSAPP",
		idioma: "es",
		tipoConsulta: "TRACKING",
		idPedido: "P-1003",
		mensaje: "Quiero saber el estado de mi pedido",
		fechaConsulta: "2026-06-17T12:15:00.000Z",
		estadoAgente: "RECIBIDA",
		respuestaAutomatica: null,
	},
	{
		idConsulta: "Q-4002",
		idCliente: "CL-001",
		tipoCliente: "B2B",
		canal: "EMAIL",
		idioma: "en",
		tipoConsulta: "DEVOLUCION",
		idPedido: "P-1002",
		mensaje: "Please confirm return status",
		fechaConsulta: "2026-06-18T08:45:00.000Z",
		estadoAgente: "RESPONDIDA_AUTOMATICAMENTE",
		respuestaAutomatica: "Return requested and pending carrier pickup.",
	},
];

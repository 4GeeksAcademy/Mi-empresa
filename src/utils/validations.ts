import type {
	ConsultaCliente,
	Devolucion,
	IncidenciaTransportista,
	Pedido,
	Transportista,
} from "../types/models.js";

function esFechaValida(valor: string): boolean {
	return !Number.isNaN(Date.parse(valor));
}

function validarFechaMayorOIgual(
	fechaInicio: string,
	fechaFin: string,
	nombreInicio: string,
	nombreFin: string,
	errores: string[],
): void {
	// Solo compara cronologia cuando ambas fechas son parseables para evitar falsos positivos.
	if (
		esFechaValida(fechaInicio) &&
		esFechaValida(fechaFin) &&
		new Date(fechaFin).getTime() < new Date(fechaInicio).getTime()
	) {
		errores.push(`${nombreFin} no puede ser anterior a ${nombreInicio}`);
	}
}

export function validarTransportista(transportista: Transportista): string[] {
	const errores: string[] = [];

	if (!transportista.idTransportista.trim()) {
		errores.push("Transportista.idTransportista es obligatorio");
	}

	if (!transportista.nombre.trim()) {
		errores.push("Transportista.nombre es obligatorio");
	}

	if (!(transportista.pesoMaximoKg > 0)) {
		errores.push("Transportista.pesoMaximoKg debe ser mayor que 0");
	}

	if (transportista.destinosDisponibles.length === 0) {
		errores.push("Transportista.destinosDisponibles no puede estar vacio");
	}

	if (transportista.urgenciasSoportadas.length === 0) {
		errores.push("Transportista.urgenciasSoportadas no puede estar vacio");
	}

	if (!transportista.apiTrackingDisponible) {
		errores.push(
			"Transportista.apiTrackingDisponible debe ser true para centralizar tracking en tiempo real",
		);
	}

	return errores;
}

export function validarPedido(pedido: Pedido): string[] {
	const errores: string[] = [];

	if (!pedido.idPedido.trim()) errores.push("Pedido.idPedido es obligatorio");
	if (!pedido.idCliente.trim()) errores.push("Pedido.idCliente es obligatorio");
	if (!pedido.idTransportista.trim()) {
		errores.push("Pedido.idTransportista es obligatorio");
	}

	if (!(pedido.pesoKg > 0)) {
		errores.push("Pedido.pesoKg debe ser mayor que 0");
	}

	if (!esFechaValida(pedido.fechaCreacion)) {
		errores.push("Pedido.fechaCreacion debe ser una fecha valida");
	}

	if (!esFechaValida(pedido.fechaEntregaEstimada)) {
		errores.push("Pedido.fechaEntregaEstimada debe ser una fecha valida");
	}

	validarFechaMayorOIgual(
		pedido.fechaCreacion,
		pedido.fechaEntregaEstimada,
		"Pedido.fechaCreacion",
		"Pedido.fechaEntregaEstimada",
		errores,
	);

	if (pedido.fechaEntregaReal !== null && !esFechaValida(pedido.fechaEntregaReal)) {
		errores.push("Pedido.fechaEntregaReal debe ser una fecha valida o null");
	}

	if (
		pedido.estadoTracking === "ENTREGADO" &&
		(pedido.fechaEntregaReal === null || !esFechaValida(pedido.fechaEntregaReal))
	) {
		// ENTREGADO implica evidencia temporal de entrega para trazabilidad operativa.
		errores.push("Pedido ENTREGADO requiere fechaEntregaReal valida");
	}

	if (pedido.estadoTracking !== "ENTREGADO" && pedido.fechaEntregaReal !== null) {
		errores.push("Pedido.fechaEntregaReal solo debe existir si estadoTracking es ENTREGADO");
	}

	return errores;
}

export function validarPedidoConTransportista(
	pedido: Pedido,
	transportista: Transportista,
): string[] {
	const errores: string[] = [];

	if (pedido.idTransportista !== transportista.idTransportista) {
		errores.push("Pedido.idTransportista no coincide con el transportista proporcionado");
	}

	if (!transportista.activo) {
		errores.push("El transportista debe estar activo para asignar pedidos");
	}

	if (!transportista.destinosDisponibles.includes(pedido.destino)) {
		errores.push(
			"El transportista no cubre el destino del pedido para la seleccion por destino",
		);
	}

	if (pedido.pesoKg > transportista.pesoMaximoKg) {
		errores.push(
			"El pedido supera el peso permitido por el transportista para la seleccion por peso",
		);
	}

	if (!transportista.urgenciasSoportadas.includes(pedido.urgencia)) {
		errores.push(
			"El transportista no soporta la urgencia del pedido para la seleccion por urgencia",
		);
	}

	return errores;
}

export function validarDevolucion(devolucion: Devolucion): string[] {
	const errores: string[] = [];

	if (!devolucion.idDevolucion.trim()) {
		errores.push("Devolucion.idDevolucion es obligatorio");
	}
	if (!devolucion.idPedido.trim()) errores.push("Devolucion.idPedido es obligatorio");
	if (!devolucion.motivo.trim()) errores.push("Devolucion.motivo es obligatorio");

	if (!esFechaValida(devolucion.fechaSolicitud)) {
		errores.push("Devolucion.fechaSolicitud debe ser una fecha valida");
	}

	if (devolucion.fechaResolucion !== null && !esFechaValida(devolucion.fechaResolucion)) {
		errores.push("Devolucion.fechaResolucion debe ser una fecha valida o null");
	}

	const estadoFinal: boolean =
		devolucion.estadoDevolucion === "RECHAZADA" ||
		devolucion.estadoDevolucion === "CERRADA";

	// Los estados finales cierran el ciclo de la devolucion y deben registrar fecha de cierre.
	if (estadoFinal && devolucion.fechaResolucion === null) {
		errores.push("Devolucion en estado final requiere fechaResolucion");
	}

	if (!estadoFinal && devolucion.fechaResolucion !== null) {
		errores.push("Devolucion abierta/en proceso no debe incluir fechaResolucion");
	}

	if (devolucion.fechaResolucion !== null) {
		validarFechaMayorOIgual(
			devolucion.fechaSolicitud,
			devolucion.fechaResolucion,
			"Devolucion.fechaSolicitud",
			"Devolucion.fechaResolucion",
			errores,
		);
	}

	return errores;
}

export function validarIncidenciaTransportista(
	incidencia: IncidenciaTransportista,
): string[] {
	const errores: string[] = [];

	if (!incidencia.idIncidencia.trim()) {
		errores.push("IncidenciaTransportista.idIncidencia es obligatorio");
	}
	if (!incidencia.idPedido.trim()) {
		errores.push("IncidenciaTransportista.idPedido es obligatorio");
	}
	if (!incidencia.idTransportista.trim()) {
		errores.push("IncidenciaTransportista.idTransportista es obligatorio");
	}
	if (!incidencia.descripcion.trim()) {
		errores.push("IncidenciaTransportista.descripcion es obligatorio");
	}

	if (!esFechaValida(incidencia.fechaReporte)) {
		errores.push("IncidenciaTransportista.fechaReporte debe ser una fecha valida");
	}

	if (incidencia.fechaResolucion !== null && !esFechaValida(incidencia.fechaResolucion)) {
		errores.push("IncidenciaTransportista.fechaResolucion debe ser una fecha valida o null");
	}

	if (
		incidencia.estadoIncidencia === "RESUELTA" &&
		(incidencia.fechaResolucion === null || !esFechaValida(incidencia.fechaResolucion))
	) {
		errores.push("IncidenciaTransportista RESUELTA requiere fechaResolucion valida");
	}

	if (
		incidencia.estadoIncidencia !== "RESUELTA" &&
		incidencia.fechaResolucion !== null
	) {
		errores.push(
			"IncidenciaTransportista.fechaResolucion solo debe existir si estadoIncidencia es RESUELTA",
		);
	}

	if (incidencia.fechaResolucion !== null) {
		validarFechaMayorOIgual(
			incidencia.fechaReporte,
			incidencia.fechaResolucion,
			"IncidenciaTransportista.fechaReporte",
			"IncidenciaTransportista.fechaResolucion",
			errores,
		);
	}

	return errores;
}

export function validarConsultaCliente(consulta: ConsultaCliente): string[] {
	const errores: string[] = [];

	if (!consulta.idConsulta.trim()) {
		errores.push("ConsultaCliente.idConsulta es obligatorio");
	}
	if (!consulta.idCliente.trim()) {
		errores.push("ConsultaCliente.idCliente es obligatorio");
	}
	if (!consulta.mensaje.trim()) {
		errores.push("ConsultaCliente.mensaje es obligatorio");
	}

	if (!esFechaValida(consulta.fechaConsulta)) {
		errores.push("ConsultaCliente.fechaConsulta debe ser una fecha valida");
	}

	if (consulta.idioma !== "es" && consulta.idioma !== "en") {
		errores.push("ConsultaCliente.idioma solo puede ser es o en");
	}

	if (consulta.canal !== "EMAIL" && consulta.canal !== "WHATSAPP") {
		errores.push("ConsultaCliente.canal solo puede ser EMAIL o WHATSAPP");
	}

	if (consulta.idPedido === null) {
		errores.push(
			"ConsultaCliente.idPedido es obligatorio para consultas de pedido, tracking, devolucion o incidencia",
		);
	}

	if (
		consulta.estadoAgente === "RESPONDIDA_AUTOMATICAMENTE" &&
		(consulta.respuestaAutomatica === null || !consulta.respuestaAutomatica.trim())
	) {
		// Si el agente reporta respuesta automatica, debe persistirse el contenido enviado al cliente.
		errores.push(
			"ConsultaCliente RESPONDIDA_AUTOMATICAMENTE requiere respuestaAutomatica",
		);
	}

	if (
		consulta.estadoAgente !== "RESPONDIDA_AUTOMATICAMENTE" &&
		consulta.respuestaAutomatica !== null
	) {
		errores.push(
			"ConsultaCliente.respuestaAutomatica solo debe existir si estadoAgente es RESPONDIDA_AUTOMATICAMENTE",
		);
	}

	return errores;
}

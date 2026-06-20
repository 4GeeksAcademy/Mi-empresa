import type {
	ConsultaCliente,
	Devolucion,
	IncidenciaTransportista,
	Pedido,
	TipoConsulta,
} from "../types/models.js";

export function countByCategory<T, K extends string>(
	items: T[],
	keySelector: (item: T) => K,
): Record<K, number> {
	return items.reduce<Record<K, number>>((acc, item) => {
		const key: K = keySelector(item);
		const current: number = acc[key] ?? 0;

		acc[key] = current + 1;
		return acc;
	}, {} as Record<K, number>);
}

export function sumBy<T>(
	items: T[],
	valueSelector: (item: T) => number,
): number {
	return items.reduce((total, item) => total + valueSelector(item), 0);
}

export function averageBy<T>(
	items: T[],
	valueSelector: (item: T) => number,
): number {
	if (items.length === 0) {
		return 0;
	}

	return sumBy(items, valueSelector) / items.length;
}

export function maxBy<T>(
	items: T[],
	valueSelector: (item: T) => number,
): T | null {
	if (items.length === 0) {
		return null;
	}

	return items.reduce((currentMax, item) => {
		return valueSelector(item) > valueSelector(currentMax) ? item : currentMax;
	});
}

export function minBy<T>(
	items: T[],
	valueSelector: (item: T) => number,
): T | null {
	if (items.length === 0) {
		return null;
	}

	return items.reduce((currentMin, item) => {
		return valueSelector(item) < valueSelector(currentMin) ? item : currentMin;
	});
}

export interface ReporteTrackFlow {
	totalPedidos: number;
	totalConsultas: number;
	totalDevoluciones: number;
	totalIncidencias: number;
	pesoTotalKg: number;
	pesoPromedioKg: number;
	pedidoMayorPeso: Pedido | null;
	pedidoMenorPeso: Pedido | null;
	consultasPorTipo: Record<TipoConsulta, number>;
}

const BASE_TIPO_CONSULTA: Record<TipoConsulta, number> = {
	PEDIDO: 0,
	TRACKING: 0,
	DEVOLUCION: 0,
	INCIDENCIA: 0,
};

export function contarConsultasPorTipo(
	consultas: ConsultaCliente[],
): Record<TipoConsulta, number> {
	const conteoParcial: Record<TipoConsulta, number> = countByCategory(
		consultas,
		(consulta: ConsultaCliente) => consulta.tipoConsulta,
	);

	return {
		...BASE_TIPO_CONSULTA,
		...conteoParcial,
	};
}

export function calcularPesoTotalPedidos(pedidos: Pedido[]): number {
	return sumBy(pedidos, (pedido: Pedido) => pedido.pesoKg);
}

export function calcularPesoPromedioPedidos(pedidos: Pedido[]): number {
	return averageBy(pedidos, (pedido: Pedido) => pedido.pesoKg);
}

export function obtenerPedidoMayorPeso(pedidos: Pedido[]): Pedido | null {
	return maxBy(pedidos, (pedido: Pedido) => pedido.pesoKg);
}

export function obtenerPedidoMenorPeso(pedidos: Pedido[]): Pedido | null {
	return minBy(pedidos, (pedido: Pedido) => pedido.pesoKg);
}

export function generarReporteTrackFlow(
	pedidos: Pedido[],
	consultas: ConsultaCliente[],
	devoluciones: Devolucion[],
	incidencias: IncidenciaTransportista[],
): ReporteTrackFlow {
	return {
		totalPedidos: pedidos.length,
		totalConsultas: consultas.length,
		totalDevoluciones: devoluciones.length,
		totalIncidencias: incidencias.length,
		pesoTotalKg: calcularPesoTotalPedidos(pedidos),
		pesoPromedioKg: calcularPesoPromedioPedidos(pedidos),
		pedidoMayorPeso: obtenerPedidoMayorPeso(pedidos),
		pedidoMenorPeso: obtenerPedidoMenorPeso(pedidos),
		consultasPorTipo: contarConsultasPorTipo(consultas),
	};
}

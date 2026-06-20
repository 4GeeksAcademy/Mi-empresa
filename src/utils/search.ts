import type { Pedido } from "../types/models.js";

export function linearSearch<T>(
	items: T[],
	predicate: (item: T) => boolean,
): T | null {
	for (const item of items) {
		if (predicate(item)) {
			return item;
		}
	}

	return null;
}

export function buscarPedidoLinealPorId(
	pedidos: Pedido[],
	idPedido: string,
): Pedido | null {
	return linearSearch(pedidos, (pedido: Pedido) => pedido.idPedido === idPedido);
}

export function buscarPedidoBinarioPorPeso(
	pedidosOrdenadosPorPeso: Pedido[],
	pesoKgObjetivo: number,
): Pedido | null {
	return binarySearchByNumber(
		pedidosOrdenadosPorPeso,
		pesoKgObjetivo,
		(pedido: Pedido) => pedido.pesoKg,
	);
}

export function binarySearchByNumber<T>(
	items: T[],
	target: number,
	valueSelector: (item: T) => number,
): T | null {
	let left: number = 0;
	let right: number = items.length - 1;

	// El algoritmo descarta media lista en cada iteracion asumiendo items ya ordenados por valueSelector.
	while (left <= right) {
		const middle: number = Math.floor((left + right) / 2);
		const item: T | undefined = items[middle];

		if (!item) {
			return null;
		}

		const value: number = valueSelector(item);

		if (value === target) {
			return item;
		}

		if (value < target) {
			left = middle + 1;
		} else {
			right = middle - 1;
		}
	}

	return null;
}
